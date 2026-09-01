"""
05_reasoning_effort.py — reasoning effort, modes, and visible reasoning summaries.

Concepts:
  REQUEST  :
    reasoning = {
        "effort":  "none" | "low" | "medium" | "high" | "xhigh" | "max",
        "summary": "auto" | "concise" | "detailed" | None,
        "mode":    "standard" | "pro",                    # NEW in gpt-5.6
        "context": "auto" | "current_turn" | "all_turns", # NEW in gpt-5.6
    }

  RESPONSE :
    output[0] MAY be a `reasoning` item (gpt-5.6 skips it when it decides
    the prompt doesn't need thinking — see script 01):
      .summary  — list of summary objects (only populated if summary='auto')
                  each summary has .text and .type='summary_text'
    usage.output_tokens_details.reasoning_tokens
      — internal thinking tokens. BILLED AS OUTPUT but reported separately.
    response.reasoning — echoes the resolved effort/mode/context/summary.

What changed from gpt-5 → gpt-5.6:
  - "minimal" is GONE. Sending it returns 400 unsupported_value. The
    replacement is "none", which truly disables reasoning (0 reasoning
    tokens, no reasoning item in output[]).
  - Two new levels above "high": "xhigh" and "max".
  - reasoning.mode="pro" — a heavier, multi-sample thinking mode (the
    response echoes mode="pro"; input_tokens jump ~40× on the same prompt,
    which is the parallel-sampling cost showing up in usage).
  - reasoning.context — how much prior conversation the model's reasoning
    may consider. "all_turns" is the default; "current_turn" scopes it to
    the newest turn; "auto" lets the server pick (resolved to all_turns in
    our run).
  - Reasoning is now ADAPTIVE: at effort="medium" a trivial prompt yields
    no reasoning item at all. This is the same idea as Anthropic's
    {type: "adaptive"} thinking, so the two providers now converge.

Run:  .venv/bin/python codex/05_reasoning_effort.py
"""
from _common import client, MODEL, section, dump

PUZZLE = (
    "A snail climbs a 30 ft well. Each day it climbs 3 ft, each night "
    "it slips back 2 ft. How many days until it reaches the top? "
    "Think it through."
)


# ============================================================
#  Reasoning with visible summary
# ============================================================
section("reasoning effort=medium, summary=auto")

resp = client.responses.create(
    model=MODEL,
    input=PUZZLE,
    reasoning={"effort": "medium", "summary": "auto"},
)

# Walk the output items. Reasoning items come first; message items follow.
for i, item in enumerate(resp.output):
    print(f"\noutput[{i}].type = {item.type!r}")
    if item.type == "reasoning":
        summaries = item.summary or []
        print(f"  summaries: {len(summaries)} block(s)")
        for j, s in enumerate(summaries):
            print(f"  summary[{j}].type = {s.type!r}")
            print(f"  summary[{j}].text =\n{s.text}")
    elif item.type == "message":
        for block in item.content:
            if block.type == "output_text":
                print(f"  final answer:\n  {block.text}")

dump(resp.reasoning, "response.reasoning (resolved knobs echoed back)")
dump(resp.usage, "usage (note reasoning_tokens are billed as output)")


# ============================================================
#  Comparison run — effort='none' (reasoning fully off)
# ============================================================
section("effort=none — for comparison")

resp_none = client.responses.create(
    model=MODEL,
    input=PUZZLE.replace("Think it through.", "Just give the number of days, nothing else."),
    reasoning={"effort": "none"},
)
print(f"answer       : {resp_none.output_text!r}")
print(f"item types   : {[i.type for i in resp_none.output]}   <-- no reasoning item")
print(f"reasoning_tk : {resp_none.usage.output_tokens_details.reasoning_tokens}")
print(f"output_tk    : {resp_none.usage.output_tokens}")


# ============================================================
#  The whole effort ladder on one prompt
# ============================================================
section("effort ladder: none → max (same puzzle)")
print(f"{'effort':8} {'reasoning_tk':>12} {'output_tk':>10}  answer (first 40 chars)")
for effort in ["none", "low", "medium", "high", "xhigh", "max"]:
    r = client.responses.create(model=MODEL, input=PUZZLE, reasoning={"effort": effort})
    d = r.usage.output_tokens_details
    print(f"{effort:8} {d.reasoning_tokens:>12} {r.usage.output_tokens:>10}  "
          f"{r.output_text[:40]!r}")


# ============================================================
#  reasoning.mode = "pro"
# ============================================================
section("reasoning.mode='pro' (multi-sample thinking)")
r_pro = client.responses.create(
    model=MODEL,
    input=PUZZLE,
    reasoning={"effort": "medium", "mode": "pro"},
)
print(f"mode echoed   : {r_pro.reasoning.mode}")
print(f"answer        : {r_pro.output_text[:60]!r}")
print(f"input_tokens  : {r_pro.usage.input_tokens}   <-- compare with ~45 in standard mode")
print(f"reasoning_tk  : {r_pro.usage.output_tokens_details.reasoning_tokens}")
print(f"output_tk     : {r_pro.usage.output_tokens}")


# ============================================================
#  Knob reference
# ============================================================
section("REASONING KNOBS")
print("""\
effort levels (gpt-5.6):
  none    — reasoning OFF. 0 reasoning_tokens, no reasoning item. (replaces "minimal")
  low     — quick; light reasoning
  medium  — default; balanced. ADAPTIVE: may emit no reasoning on easy prompts.
  high    — deeper reasoning
  xhigh   — NEW: more than high
  max     — NEW: the model's ceiling

mode:
  standard — default
  pro      — NEW: heavier multi-sample thinking; much higher input_tokens

context:
  all_turns    — default; reasoning may consider the whole conversation
  current_turn — NEW: scope reasoning to the newest turn only
  auto         — let the server choose

summary levels (only relevant when effort != none):
  None        — no visible reasoning (the default)
  'concise'   — short summary
  'detailed'  — longer summary
  'auto'      — model picks an appropriate level

Caveat: reasoning_tokens are BILLED AS OUTPUT. A max-effort or pro-mode
call can spend many tokens you never see in output_text. Always inspect
output_tokens_details.reasoning_tokens (and input_tokens in pro mode).
""")
