from __future__ import annotations

import sys

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError, ProfileNotFound
from rich.console import Console

from .cloudwatch import LOG_GROUP

console = Console()


def make_client(region: str | None, profile: str | None):
    """Create a CloudWatch Logs boto3 client, exiting with a readable error on failure."""
    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        resolved_region = session.region_name
        return session.client("logs")
    except ProfileNotFound as exc:
        console.print(f"[red]AWS profile not found:[/red] {exc}")
        sys.exit(1)
    except NoCredentialsError:
        console.print(
            "[red]No AWS credentials found.[/red] "
            "Configure them with [bold]aws configure[/bold] or set "
            "[bold]AWS_ACCESS_KEY_ID[/bold] / [bold]AWS_SECRET_ACCESS_KEY[/bold]."
        )
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


def handle_client_error(exc: ClientError) -> None:
    """Print a human-readable message for a CloudWatch ClientError."""
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
