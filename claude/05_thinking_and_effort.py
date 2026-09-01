"""
05_thinking_and_effort.py — adaptive thinking, effort, and the `display` knob.

Concepts:
  REQUEST  :
    thinking      : {"type": "adaptive"}                            — Claude decides depth
                    {"type": "adaptive", "display": "summarized"}   — opt back into visible reasoning
                    {"type": "adaptive", "display": "omitted"}      — default on Opus 4.8
                    {"type": "disabled"}                            — turn it off entirely
                    (older models: {"type": "enabled", "budget_tokens": N} — removed on Opus 4.8)
    output_config : {"effort": "low" | "medium" | "high" | "xhigh" | "max"}
                    Effort controls overall token spend AND thinking depth.
                    "max" and "xhigh" are Opus-tier only.

  RESPONSE :
    A thinking-type block precedes the text block(s) when thinking is enabled
    AND display != "omitted":
      content[0] = ThinkingBlock(thinking="<reasoning text>", signature="<opaque>")
      content[1] = TextBlock(text="<final answer>")
    The `signature` is an opaque token that must be preserved verbatim if you
    pass the thinking block back in a follow-up message (e.g. tool-use loops
    with interleaved thinking).

Why adaptive: the legacy `budget_tokens` knob forced you to pick a fixed
thinking budget for every request — wasteful for easy questions, too small
for hard ones. Adaptive lets the model self-calibrate per request.

Why `display`: on Opus 4.8 the default is "omitted" (thinking blocks still
exist in the response, but their `.thinking` field is empty). Set
display="summarized" to see a human-readable summary of the reasoning.
"""
from _common import client, MODEL, section, dump


# ============================================================
#  Adaptive thinking + visible summary + medium effort
# ============================================================
section("adaptive thinking, display=summarized, effort=medium")

resp = client.messages.create(
    model=MODEL,
    max_tokens=2048,
    thinking={"type": "adaptive", "display": "summarized"},
    output_config={"effort": "medium"},
    messages=[
        {
            "role": "user",
            "content": (
                "A snail climbs a 30 ft well. Each day it climbs 3 ft, "
                "each night it slips down 2 ft. How many days until it "
                "reaches the top? Think it through."
            ),
        }
    ],
)

# Walk the content list. Thinking blocks always precede text blocks.
for i, block in enumerate(resp.content):
    print(f"\ncontent[{i}].type = {block.type!r}")
    if block.type == "thinking":
        print(f"content[{i}].thinking:\n{block.thinking}")
        print(f"content[{i}].signature: {block.signature[:60]}... (truncated, len={len(block.signature)})")
    elif block.type == "text":
        print(f"content[{i}].text:\n{block.text}")

dump(resp.usage, "usage (note output_tokens covers thinking + text)")


# ============================================================
#  Comparison run — thinking disabled
# ============================================================
section("thinking disabled — for comparison")

resp_off = client.messages.create(
    model=MODEL,
    max_tokens=512,
    thinking={"type": "disabled"},
    messages=[{"role": "user", "content": "Same snail puzzle. Just give the number of days, nothing else."}],
)

for block in resp_off.content:
    if block.type == "text":
        print(f"answer: {block.text!r}")
print(f"output_tokens (no thinking): {resp_off.usage.output_tokens}")


# ============================================================
#  Effort levels — what to pick
# ============================================================
section("EFFORT LEVELS")
print("""\
low      — short, scoped tasks; latency-sensitive; chat/classification
medium   — balanced cost/quality; default for most application code
high     — intelligence-sensitive work; recommended minimum for hard tasks
xhigh    — Opus 4.8 only; best for coding and agentic loops (Claude Code default)
max      — Opus-tier only; highest quality, highest cost; may overthink

Effort interacts with adaptive thinking: higher effort means the model is
more likely to invoke thinking AND to think more deeply when it does.
""")
