# bedrock-lens

Real-time token usage and cost monitoring for AWS Bedrock — because Cost Explorer won't tell you until tomorrow.

| Model             | Calls | Input Tokens | Output Tokens | Total Tokens | Est. Cost |
|-------------------|------:|-------------:|--------------:|-------------:|----------:|
| Claude Opus 4     |     2 |       12,540 |         3,812 |       16,352 |   $0.4746 |
| Claude Sonnet 4   |    14 |       48,300 |        11,220 |       59,520 |   $0.3132 |
| Claude Haiku 4    |    38 |       63,807 |         9,441 |       73,248 |   $0.0888 |
| Llama 3.1 70B     |     5 |        4,200 |         1,830 |        6,030 |   $0.0060 |
| **TOTAL**         |    59 |      128,847 |        26,303 |      155,150 |   $0.8826 |

## The problem

When running Bedrock agents, you're flying blind. AWS Cost Explorer has a 24–48 hour lag. CloudWatch has live data, but getting to it requires knowing the log group name, converting dates to epoch milliseconds, parsing deeply nested JSON, and doing the cost math yourself.

There's no `bedrock usage` command. This is that command.

## Install

```bash
uv tool install git+https://github.com/OmarCodes022/bedrock-lens
```

Or from source:

```bash
git clone https://github.com/OmarCodes022/bedrock-lens
cd bedrock-lens
uv tool install .
```

## Usage

```bash
bedrock-lens                        # today's usage (default)
bedrock-lens --yesterday
bedrock-lens --week
bedrock-lens --since 2h             # last 2 hours
bedrock-lens --since 30m            # last 30 minutes
bedrock-lens --since 1d             # last 1 day
bedrock-lens --live                 # tail mode, refreshes every 5s
bedrock-lens --since 1h --live      # live tail for the last hour
bedrock-lens --live --threshold 2   # alert when spend crosses $2
bedrock-lens --setup                # one-time setup wizard
```

```bash
# different profile / region
bedrock-lens --profile my-profile --region us-west-2
```

## First-time setup

Bedrock doesn't log invocations by default. Run the setup wizard once per AWS account:

```bash
bedrock-lens --setup
```

This creates the CloudWatch log group, an IAM role for Bedrock to write to it, and enables model invocation logging. Takes about 10 seconds. After that, every Bedrock call shows up within ~30 seconds.

If you don't have IAM permissions to create roles, the wizard prints the exact policies and CLI command to hand off to your admin.

## How it works

Bedrock writes a JSON record to `/aws/bedrock/model-invocations` in CloudWatch for every model call. Each record contains the model ID, input token count, and output token count. `bedrock-lens` reads those records, applies per-model pricing, and renders the table.

Live mode (`--live`) polls every 5 seconds with a 90-second overlap window to handle CloudWatch's ingestion delay, deduplicating events by ID so nothing gets double-counted.

## Supported models

Claude (Haiku, Sonnet, Opus — v3 through v4), Amazon Titan, Meta Llama 3 / 3.1 / 3.2, Mistral, Mixtral, Cohere Command R / R+, AI21 Jamba.

Pricing is per the AWS on-demand rates for `us-east-1`. Unknown models show `N/A` for cost but still display token counts.

## Requirements

- Python 3.9+
- AWS credentials with `logs:FilterLogEvents` on `/aws/bedrock/model-invocations`
- Bedrock model invocation logging enabled (run `--setup` if not)
