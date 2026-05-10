from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

import boto3
import click
from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError, ProfileNotFound
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from .cloudwatch import iter_log_events, aggregate, get_time_range, LOG_GROUP
from .display import build_table, total_cost
from .setup_cmd import run_setup

console = Console()

_POLL_SECONDS = 5
_LIVE_OVERLAP_MS = 90_000  # re-fetch this far back each poll to catch delayed ingestion


def _make_client(region: str | None, profile: str | None):
    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        resolved_region = session.region_name
        client = session.client("logs")
        return client
    except ProfileNotFound as exc:
        console.print(f"[red]AWS profile not found:[/red] {exc}")
        sys.exit(1)
    except NoRegionError:
        if resolved_region:
            console.print(
                f"[red]CloudWatch Logs is not available in region: {resolved_region}[/red]\n"
                "Pass [bold]--region[/bold] with a supported region."
            )
        else:
            console.print(
                "[red]No AWS region configured.[/red] "
                "Pass [bold]--region[/bold] or set [bold]AWS_DEFAULT_REGION[/bold]."
            )
        sys.exit(1)


def _period_label(period: str) -> str:
    now = datetime.now()
    if period == "today":
        return f"Today ({now.strftime('%Y-%m-%d')})"
    if period == "yesterday":
        from datetime import timedelta
        y = now - timedelta(days=1)
        return f"Yesterday ({y.strftime('%Y-%m-%d')})"
    if period == "week":
        return "Past 7 Days"
    return period


def _handle_client_error(exc: ClientError) -> None:
    code = exc.response["Error"]["Code"]
    msg  = exc.response["Error"]["Message"]
    if code == "ResourceNotFoundException":
        console.print(f"[yellow]Log group not found:[/yellow] {LOG_GROUP}")
        console.print(
            "[dim]Run [bold]bedrock-usage --setup[/bold] to enable "
            "Bedrock model invocation logging.[/dim]"
        )
    elif code in ("AccessDeniedException", "UnauthorizedException"):
        console.print(f"[red]Access denied:[/red] {msg}")
        console.print(
            "[dim]Your credentials need [bold]logs:FilterLogEvents[/bold] "
            f"on [bold]{LOG_GROUP}[/bold].[/dim]"
        )
    else:
        console.print(f"[red]AWS error ({code}):[/red] {msg}")


# ── CLI definition ────────────────────────────────────────────────────────────

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--today",     "period", flag_value="today",     default=True,
              help="Show today's usage (default).")
@click.option("--yesterday", "period", flag_value="yesterday",
              help="Show yesterday's usage.")
@click.option("--week",      "period", flag_value="week",
              help="Show the past 7 days.")
@click.option("--live",  is_flag=True,
              help="Tail mode — refresh table as new calls arrive.")
@click.option("--threshold", type=float, default=None, metavar="DOLLARS",
              help="Print a warning when total spend crosses this amount.")
@click.option("--region",  default=None, envvar="AWS_DEFAULT_REGION",
              help="AWS region (default: from env / ~/.aws/config).")
@click.option("--profile", default=None, envvar="AWS_PROFILE",
              help="AWS named profile.")
@click.option("--setup", is_flag=True, is_eager=True,
              help="Run one-time setup to enable Bedrock model invocation logging.")
def main(
    period: str,
    live: bool,
    threshold: float | None,
    region: str | None,
    profile: str | None,
    setup: bool,
) -> None:
    """Monitor AWS Bedrock token usage and costs in real time.

    \b
    Examples
    --------
      bedrock-usage                    # today's usage
      bedrock-usage --week             # past 7 days
      bedrock-usage --live             # live tail, refreshes every 5 s
      bedrock-usage --live --threshold 2.00   # alert at $2
      bedrock-usage --setup            # one-time setup wizard
    """
    if setup:
        run_setup(region, profile)
        return

    try:
        client = _make_client(region, profile)
    except NoCredentialsError:
        console.print(
            "[red]No AWS credentials found.[/red] "
            "Configure them with [bold]aws configure[/bold] or set "
            "[bold]AWS_ACCESS_KEY_ID[/bold] / [bold]AWS_SECRET_ACCESS_KEY[/bold]."
        )
        sys.exit(1)

    if live:
        _run_live(client, period, threshold)
    else:
        _run_once(client, period, threshold)


# ── One-shot display ──────────────────────────────────────────────────────────

def _run_once(client, period: str, threshold: float | None) -> None:
    start_ms, end_ms = get_time_range(period)
    label = _period_label(period)

    console.print(f"[dim]Fetching {label} from CloudWatch…[/dim]")

    try:
        records = list(iter_log_events(client, start_ms, end_ms))
    except ClientError as exc:
        _handle_client_error(exc)
        return

    usage = aggregate(records)

    if not usage:
        console.print(f"\n[yellow]No Bedrock invocations found for {label}.[/yellow]")
        console.print(
            "[dim]If you haven't enabled logging yet, run "
            "[bold]bedrock-usage --setup[/bold].[/dim]"
        )
        return

    console.print()
    console.print(build_table(usage, title=f"Bedrock Usage — {label}"))
    console.print()

    if threshold is not None:
        cost = total_cost(usage)
        if cost >= threshold:
            console.print(
                f"[bold red]⚠  THRESHOLD EXCEEDED:[/bold red]  "
                f"${cost:.4f} ≥ ${threshold:.2f}"
            )


# ── Live tail mode ────────────────────────────────────────────────────────────

def _run_live(client, period: str, threshold: float | None) -> None:
    start_ms, _ = get_time_range(period)
    label        = _period_label(period)

    # Incremental usage dict; updated in-place so we never re-aggregate everything.
    usage: dict[str, dict] = {}
    seen_ids: set[str] = set()
    threshold_alerted = False

    def ingest(from_ms: int) -> int:
        """Fetch events from from_ms to now, merge into usage. Returns new count."""
        to_ms   = int(datetime.now(timezone.utc).timestamp() * 1000)
        new_cnt = 0
        try:
            for r in iter_log_events(client, from_ms, to_ms):
                eid = r.get("_eventId", "")
                if eid and eid in seen_ids:
                    continue
                if eid:
                    seen_ids.add(eid)
                model = r.get("modelId", "unknown")
                inp   = (r.get("input")  or {}).get("inputTokenCount")  or 0
                out   = (r.get("output") or {}).get("outputTokenCount") or 0
                if model not in usage:
                    usage[model] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
                usage[model]["calls"]        += 1
                usage[model]["input_tokens"] += inp
                usage[model]["output_tokens"] += out
                new_cnt += 1
        except ClientError as exc:
            _handle_client_error(exc)
        return new_cnt

    def render(last_update: str) -> Panel:
        if not usage:
            body = Text("Waiting for Bedrock invocations…", style="dim italic")
        else:
            body = build_table(usage)
        return Panel(
            body,
            title=f"[bold]Bedrock Live Monitor[/bold]  [dim]—  {label}[/dim]",
            subtitle=(
                f"[dim]Last updated: {last_update}"
                f"  •  refreshing every {_POLL_SECONDS}s"
                f"  •  Ctrl+C to exit[/dim]"
            ),
            border_style="blue",
        )

    # Initial full load for the period, then subsequent polls cover only recent window.
    console.print("[dim]Loading initial data…[/dim]")
    ingest(start_ms)
    poll_from_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - _LIVE_OVERLAP_MS
    now_str      = datetime.now().strftime("%H:%M:%S")

    with Live(render(now_str), refresh_per_second=2, console=console) as live:
        try:
            while True:
                time.sleep(_POLL_SECONDS)

                new_cnt      = ingest(max(start_ms, poll_from_ms))
                poll_from_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - _LIVE_OVERLAP_MS
                now_str      = datetime.now().strftime("%H:%M:%S")
                live.update(render(now_str))

                if threshold is not None and not threshold_alerted:
                    cost = total_cost(usage)
                    if cost >= threshold:
                        threshold_alerted = True
                        # Pause the live display just long enough to print the alert.
                        live.stop()
                        console.print(
                            f"\n[bold red]⚠  THRESHOLD EXCEEDED:[/bold red]  "
                            f"${cost:.4f} ≥ ${threshold:.2f}\n"
                        )
                        live.start()

        except KeyboardInterrupt:
            pass

    console.print("[dim]Exited live mode.[/dim]")
