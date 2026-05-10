from __future__ import annotations

import time
from datetime import datetime, timezone

import click
from botocore.exceptions import ClientError
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from .client import make_client, handle_client_error
from .cloudwatch import iter_log_events, aggregate, get_time_range
from .display import build_table, total_cost, period_label
from .setup_cmd import run_setup

console = Console()

_POLL_SECONDS = 5
_LIVE_OVERLAP_MS = 90_000


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

    client = make_client(region, profile)

    if live:
        _run_live(client, period, threshold)
    else:
        _run_once(client, period, threshold)


# ── One-shot display ──────────────────────────────────────────────────────────

def _run_once(client, period: str, threshold: float | None) -> None:
    label = period_label(period)
    start_ms, end_ms = get_time_range(period)

    console.print(f"[dim]Fetching {label} from CloudWatch…[/dim]")

    try:
        records = list(iter_log_events(client, start_ms, end_ms))
    except ClientError as exc:
        handle_client_error(exc)
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
    label     = period_label(period)
    start_ms, _ = get_time_range(period)

    usage: dict[str, dict] = {}
    seen_ids: set[str] = set()
    threshold_alerted = False

    def ingest(from_ms: int) -> None:
        to_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
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
                usage[model]["calls"]         += 1
                usage[model]["input_tokens"]  += inp
                usage[model]["output_tokens"] += out
        except ClientError as exc:
            handle_client_error(exc)

    def render(last_update: str) -> Panel:
        body = build_table(usage) if usage else Text("Waiting for Bedrock invocations…", style="dim italic")
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

    console.print("[dim]Loading initial data…[/dim]")
    ingest(start_ms)
    poll_from_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - _LIVE_OVERLAP_MS

    with Live(render(datetime.now().strftime("%H:%M:%S")), refresh_per_second=2, console=console) as live:
        try:
            while True:
                time.sleep(_POLL_SECONDS)
                ingest(max(start_ms, poll_from_ms))
                poll_from_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - _LIVE_OVERLAP_MS
                live.update(render(datetime.now().strftime("%H:%M:%S")))

                if threshold is not None and not threshold_alerted:
                    cost = total_cost(usage)
                    if cost >= threshold:
                        threshold_alerted = True
                        console.print(
                            f"\n[bold red]⚠  THRESHOLD EXCEEDED:[/bold red]  "
                            f"${cost:.4f} ≥ ${threshold:.2f}\n"
                        )
        except KeyboardInterrupt:
            pass

    console.print("[dim]Exited live mode.[/dim]")
