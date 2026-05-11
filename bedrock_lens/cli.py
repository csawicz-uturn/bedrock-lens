from __future__ import annotations

import click

from .client import make_client
from .cloudwatch import parse_since
from .runner import run_once, run_live
from .setup_cmd import run_setup


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--today",     "period", flag_value="today",     default=True,
              help="Show today's usage (default).")
@click.option("--yesterday", "period", flag_value="yesterday",
              help="Show yesterday's usage.")
@click.option("--week",      "period", flag_value="week",
              help="Show the past 7 days.")
@click.option("--since", default=None, metavar="DURATION",
              help="Show usage for the last N seconds/minutes/hours/days (e.g. 30m, 2h, 1d).")
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
    since: str | None,
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
      bedrock-usage --since 2h         # last 2 hours
      bedrock-usage --since 30m --live # live tail for the last 30 min
      bedrock-usage --live --threshold 2.00   # alert at $2
      bedrock-usage --setup            # one-time setup wizard
    """
    if setup:
        run_setup(region, profile)
        return

    if since:
        try:
            parse_since(since)
        except ValueError as exc:
            raise click.BadParameter(str(exc), param_hint="--since") from exc

    client = make_client(region, profile)

    if live:
        run_live(client, period, threshold, since)
    else:
        run_once(client, period, threshold, since)
