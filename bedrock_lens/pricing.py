from __future__ import annotations

import json
import re

# (pattern, input_per_1M_usd, output_per_1M_usd, display_name)
# Ordered most-specific first so the first match wins.
_TABLE: list[tuple[str, float, float, str]] = [
    # Claude — Opus (most-specific version first)
    ("claude-opus-4-7",         5.50,    27.50,   "Claude Opus 4.7"),
    ("claude-opus-4-6",         5.50,    27.50,   "Claude Opus 4.6"),
    ("claude-opus-4-5",         5.50,    27.50,   "Claude Opus 4.5"),
    ("claude-opus-4-1",        15.00,    75.00,   "Claude Opus 4.1"),
    ("claude-opus-4",          15.00,    75.00,   "Claude Opus 4"),
    ("claude-3-opus",          15.00,    75.00,   "Claude 3 Opus"),
    # Claude — Sonnet
    ("claude-sonnet-4-6",       3.30,    16.50,   "Claude Sonnet 4.6"),
    ("claude-sonnet-4-5",       3.30,    16.50,   "Claude Sonnet 4.5"),
    ("claude-sonnet-4",         3.00,    15.00,   "Claude Sonnet 4"),
    ("claude-3-7-sonnet",       3.00,    15.00,   "Claude 3.7 Sonnet"),
    ("claude-3-5-sonnet",       3.00,    15.00,   "Claude 3.5 Sonnet"),
    ("claude-3-sonnet",         3.00,    15.00,   "Claude 3 Sonnet"),
    # Claude — Haiku
    ("claude-haiku-4-5",        1.10,     5.50,   "Claude Haiku 4.5"),
    ("claude-haiku-4",          1.10,     5.50,   "Claude Haiku 4"),
    ("claude-3-5-haiku",        0.80,     4.00,   "Claude 3.5 Haiku"),
    ("claude-3-haiku",          0.25,     1.25,   "Claude 3 Haiku"),
    # Amazon Titan
    ("titan-text-premier",      0.50,     1.50,   "Titan Text Premier"),
    ("titan-text-express",      0.80,     1.60,   "Titan Text Express"),
    ("titan-text-lite",         0.30,     0.40,   "Titan Text Lite"),
    # Meta Llama 3.2
    ("llama3-2-90b",            2.00,     2.00,   "Llama 3.2 90B"),
    ("llama3-2-11b",            0.16,     0.16,   "Llama 3.2 11B"),
    ("llama3-2-3b",             0.15,     0.15,   "Llama 3.2 3B"),
    ("llama3-2-1b",             0.10,     0.10,   "Llama 3.2 1B"),
    # Meta Llama 3.1
    ("llama3-1-405b",           5.32,    16.00,   "Llama 3.1 405B"),
    ("llama3-1-70b",            0.99,     0.99,   "Llama 3.1 70B"),
    ("llama3-1-8b",             0.22,     0.22,   "Llama 3.1 8B"),
    # Meta Llama 3
    ("llama3-70b",              2.65,     3.50,   "Llama 3 70B"),
    ("llama3-8b",               0.30,     0.60,   "Llama 3 8B"),
    # Mistral
    ("mistral-large",           4.00,    12.00,   "Mistral Large"),
    ("mixtral-8x7b",            0.45,     0.70,   "Mixtral 8x7B"),
    ("mistral-7b",              0.15,     0.20,   "Mistral 7B"),
    # Cohere (most-specific first)
    ("command-r-plus",          3.00,    15.00,   "Command R+"),
    ("command-r",               0.50,     1.50,   "Command R"),
    # AI21
    ("jamba-1-5-large",         2.00,     8.00,   "Jamba 1.5 Large"),
    ("jamba-1-5-mini",          0.20,     0.40,   "Jamba 1.5 Mini"),
]

_REGION_TO_LOCATION: dict[str, str] = {
    "us-east-1":      "US East (N. Virginia)",
    "us-east-2":      "US East (Ohio)",
    "us-west-1":      "US West (N. California)",
    "us-west-2":      "US West (Oregon)",
    "eu-west-1":      "Europe (Ireland)",
    "eu-west-2":      "Europe (London)",
    "eu-west-3":      "Europe (Paris)",
    "eu-central-1":   "Europe (Frankfurt)",
    "eu-north-1":     "Europe (Stockholm)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-south-1":     "Asia Pacific (Mumbai)",
    "ca-central-1":   "Canada (Central)",
    "sa-east-1":      "South America (Sao Paulo)",
}

_live_cache: dict[str, tuple[float, float, str]] | None = None


def _normalize(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _fetch_live(region: str | None) -> dict[str, tuple[float, float, str]]:
    try:
        import boto3
        location = _REGION_TO_LOCATION.get(region or "us-east-1", "US East (N. Virginia)")
        client = boto3.client('pricing', region_name='us-east-1')  # Price List API only exists in us-east-1; other regions return AccessDeniedException
        paginator = client.get_paginator('get_products')

        raw: dict[str, dict] = {}
        for page in paginator.paginate(
            ServiceCode='AmazonBedrock',
            Filters=[{'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location}],
        ):
            for p in page['PriceList']:
                obj = json.loads(p)
                attr = obj['product']['attributes']
                model_name = attr.get('model', '')
                if not model_name:
                    continue
                inference_type = attr.get('inferenceType', '')
                if inference_type not in ('Input tokens', 'Output tokens'):
                    continue
                price_per_1k = float(
                    list(
                        list(obj['terms']['OnDemand'].values())[0]['priceDimensions'].values()
                    )[0]['pricePerUnit']['USD']
                )
                key = _normalize(model_name)
                if key not in raw:
                    raw[key] = {'display': model_name}
                if 'Input' in inference_type:
                    raw[key]['input'] = price_per_1k * 1000
                else:
                    raw[key]['output'] = price_per_1k * 1000

        return {
            key: (data['input'], data['output'], data['display'])
            for key, data in raw.items()
            if 'input' in data and 'output' in data
        }
    except Exception:
        return {}


def init_pricing(region: str | None) -> None:
    global _live_cache
    _live_cache = _fetch_live(region)


def lookup(model_id: str) -> tuple[float, float, str]:
    """Return (input_per_1M, output_per_1M, display_name) for a model ID."""
    lower = model_id.lower()
    norm = _normalize(lower)

    if _live_cache:
        for key, (in_p, out_p, name) in sorted(_live_cache.items(), key=lambda x: -len(x[0])):
            if key in norm:
                return in_p, out_p, name

    for pattern, in_p, out_p, name in _TABLE:
        if pattern in lower:
            return in_p, out_p, name

    return 0.0, 0.0, model_id


def calculate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    in_p, out_p, _ = lookup(model_id)
    return (input_tokens * in_p + output_tokens * out_p) / 1_000_000
