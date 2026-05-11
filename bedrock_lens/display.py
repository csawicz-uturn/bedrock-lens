from __future__ import annotations

from datetime import datetime, timedelta

from rich import box
from rich.table import Table

from .pricing import lookup, calculate_cost


def period_label(period: str) -> str:
    now = datetime.now()
    if period == "today":
        return f"Today ({now.strftime('%Y-%m-%d')})"
    if period == "yesterday":
        y = now - timedelta(days=1)
        return f"Yesterday ({y.strftime('%Y-%m-%d')})"
    if period == "week":
        return "Past 7 Days"
    return period


def since_label(value: str) -> str:
    unit_names = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    v = value.strip().lower()
    unit = unit_names.get(v[-1], v[-1])
    amount = v[:-1].rstrip()
    amount = amount.rstrip("0").rstrip(".") if "." in amount else amount
    return f"Last {amount} {unit}"


def _fmt_tokens(n: int) -> str:
    return f"{n:,}"


def _fmt_cost(cost: float, known: bool) -> str:
    if not known:
        return "[dim]N/A[/dim]"
    return f"${cost:.4f}"


def build_table(usage: dict[str, dict], title: str = "") -> Table:
    """Build a Rich Table summarising token usage and estimated cost."""
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_footer=True,
        expand=False,
        title_style="bold",
    )
    table.add_column("Model",         style="cyan",         no_wrap=True,     footer="TOTAL")
    table.add_column("Calls",         style="bright_white", justify="right",  footer_style="bold")
    table.add_column("Input Tokens",  style="green",        justify="right",  footer_style="bold green")
    table.add_column("Output Tokens", style="yellow",       justify="right",  footer_style="bold yellow")
    table.add_column("Total Tokens",  style="white",        justify="right",  footer_style="bold")
    table.add_column("Est. Cost",     style="magenta",      justify="right",  footer_style="bold magenta")

    total_calls = total_input = total_output = 0
    total_cost = 0.0
    all_prices_known = True

    for model_id, stats in sorted(usage.items()):
        inp   = stats["input_tokens"]
        out   = stats["output_tokens"]
        calls = stats["calls"]
        in_p, out_p, display_name = lookup(model_id)
        known = in_p > 0 or out_p > 0
        cost  = calculate_cost(model_id, inp, out)

        total_calls  += calls
        total_input  += inp
        total_output += out
        total_cost   += cost
        if not known:
            all_prices_known = False

        table.add_row(
            display_name,
            str(calls),
            _fmt_tokens(inp),
            _fmt_tokens(out),
            _fmt_tokens(inp + out),
            _fmt_cost(cost, known),
        )

    table.columns[1].footer = str(total_calls)
    table.columns[2].footer = _fmt_tokens(total_input)
    table.columns[3].footer = _fmt_tokens(total_output)
    table.columns[4].footer = _fmt_tokens(total_input + total_output)
    table.columns[5].footer = _fmt_cost(total_cost, all_prices_known or total_cost > 0)

    return table


def total_cost(usage: dict[str, dict]) -> float:
    return sum(
        calculate_cost(mid, s["input_tokens"], s["output_tokens"])
        for mid, s in usage.items()
    )
