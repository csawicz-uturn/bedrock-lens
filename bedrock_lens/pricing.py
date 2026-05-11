from __future__ import annotations

# (pattern, input_per_1k_usd, output_per_1k_usd, display_name)
# Ordered most-specific first so the first match wins.
_TABLE: list[tuple[str, float, float, str]] = [
    # Claude — Opus (most-specific version first)
    ("claude-opus-4-7",         0.0055,   0.0275,  "Claude Opus 4.7"),
    ("claude-opus-4-6",         0.0055,   0.0275,  "Claude Opus 4.6"),
    ("claude-opus-4-5",         0.0055,   0.0275,  "Claude Opus 4.5"),
    ("claude-opus-4-1",         0.015,    0.075,   "Claude Opus 4.1"),
    ("claude-opus-4",           0.015,    0.075,   "Claude Opus 4"),
    ("claude-3-opus",           0.015,    0.075,   "Claude 3 Opus"),
    # Claude — Sonnet
    ("claude-sonnet-4-6",       0.0033,   0.0165,  "Claude Sonnet 4.6"),
    ("claude-sonnet-4-5",       0.0033,   0.0165,  "Claude Sonnet 4.5"),
    ("claude-sonnet-4",         0.003,    0.015,   "Claude Sonnet 4"),
    ("claude-3-7-sonnet",       0.003,    0.015,   "Claude 3.7 Sonnet"),
    ("claude-3-5-sonnet",       0.003,    0.015,   "Claude 3.5 Sonnet"),
    ("claude-3-sonnet",         0.003,    0.015,   "Claude 3 Sonnet"),
    # Claude — Haiku
    ("claude-haiku-4-5",        0.0011,   0.0055,  "Claude Haiku 4.5"),
    ("claude-haiku-4",          0.0011,   0.0055,  "Claude Haiku 4"),
    ("claude-3-5-haiku",        0.0008,   0.004,   "Claude 3.5 Haiku"),
    ("claude-3-haiku",          0.00025,  0.00125, "Claude 3 Haiku"),
    # Amazon Titan
    ("titan-text-premier",      0.0005,   0.0015,  "Titan Text Premier"),
    ("titan-text-express",      0.0008,   0.0016,  "Titan Text Express"),
    ("titan-text-lite",         0.0003,   0.0004,  "Titan Text Lite"),
    # Meta Llama 3.2
    ("llama3-2-90b",            0.002,    0.002,   "Llama 3.2 90B"),
    ("llama3-2-11b",            0.00016,  0.00016, "Llama 3.2 11B"),
    ("llama3-2-3b",             0.00015,  0.00015, "Llama 3.2 3B"),
    ("llama3-2-1b",             0.0001,   0.0001,  "Llama 3.2 1B"),
    # Meta Llama 3.1
    ("llama3-1-405b",           0.00532,  0.016,   "Llama 3.1 405B"),
    ("llama3-1-70b",            0.00099,  0.00099, "Llama 3.1 70B"),
    ("llama3-1-8b",             0.00022,  0.00022, "Llama 3.1 8B"),
    # Meta Llama 3
    ("llama3-70b",              0.00265,  0.0035,  "Llama 3 70B"),
    ("llama3-8b",               0.0003,   0.0006,  "Llama 3 8B"),
    # Mistral
    ("mistral-large",           0.004,    0.012,   "Mistral Large"),
    ("mixtral-8x7b",            0.00045,  0.0007,  "Mixtral 8x7B"),
    ("mistral-7b",              0.00015,  0.0002,  "Mistral 7B"),
    # Cohere (most-specific first)
    ("command-r-plus",          0.003,    0.015,   "Command R+"),
    ("command-r",               0.0005,   0.0015,  "Command R"),
    # AI21
    ("jamba-1-5-large",         0.002,    0.008,   "Jamba 1.5 Large"),
    ("jamba-1-5-mini",          0.0002,   0.0004,  "Jamba 1.5 Mini"),
]


def lookup(model_id: str) -> tuple[float, float, str]:
    """Return (input_per_1k, output_per_1k, display_name) for a model ID."""
    lower = model_id.lower()
    for pattern, in_p, out_p, name in _TABLE:
        if pattern in lower:
            return in_p, out_p, name
    return 0.0, 0.0, model_id


def calculate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    in_p, out_p, _ = lookup(model_id)
    return (input_tokens * in_p + output_tokens * out_p) / 1000
