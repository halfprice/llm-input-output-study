"""
06_stop_reasons.py — every reason the model stops generating.

Concepts:
  RESPONSE.stop_reason values:
    end_turn       — Claude finished naturally (your goal)
    max_tokens     — hit the max_tokens cap (output is truncated mid-thought)
    stop_sequence  — hit one of your custom stop strings (response.stop_sequence
                     tells you which one)
    tool_use       — Claude wants to call a tool (see 07_tool_use_manual.py)
    pause_turn     — server-side tool loop hit its iteration limit;
                     re-send to resume
    refusal        — Claude refused for safety reasons. response.stop_details
                     carries {category, explanation} (category is "cyber" / "bio")
    model_context_window_exceeded — total context (input + thinking + output)
                     exhausted the model's window; compact or split

  REQUEST inputs that influence stop_reason:
    max_tokens         — hard per-response ceiling (NOT visible to the model)
    stop_sequences[]   — up to 4 custom strings; generation stops if any
                         appears in the output

This script demonstrates the three reasons you can trigger from a plain
text-only request. tool_use is covered in 07_, refusal/pause_turn are
discussed at the end.
"""
from _common import client, MODEL, section, dump


# ============================================================
#  1) end_turn — the normal case
# ============================================================
section("stop_reason: end_turn")
r1 = client.messages.create(
    model=MODEL,
    max_tokens=128,
    messages=[{"role": "user", "content": "Say hello in 5 words."}],
)
print(f"text         : {r1.content[0].text!r}")
print(f"stop_reason  : {r1.stop_reason}")
print(f"stop_sequence: {r1.stop_sequence}")


# ============================================================
#  2) max_tokens — hard cap hit
# ============================================================
# Forcing a very tight cap on a verbose request guarantees truncation.
# Note: the model can't see max_tokens, so it doesn't ration its output.
section("stop_reason: max_tokens")
r2 = client.messages.create(
    model=MODEL,
    max_tokens=20,  # deliberately tiny
    messages=[{"role": "user", "content": "Explain the Internet Protocol in full detail."}],
)
print(f"text         : {r2.content[0].text!r}  <-- truncated mid-sentence")
print(f"stop_reason  : {r2.stop_reason}")
print(f"output_tokens: {r2.usage.output_tokens}  <-- equals max_tokens")


# ============================================================
#  3) stop_sequence — custom stop strings
# ============================================================
# stop_sequences is a list of up to 4 strings. The model stops as soon as it
# emits one (the stop string is NOT included in the output). Useful for
# delimited formats — e.g. stop at "</answer>" or "###".
section("stop_reason: stop_sequence")
r3 = client.messages.create(
    model=MODEL,
    max_tokens=256,
    stop_sequences=["END", "###"],
    messages=[
        {
            "role": "user",
            "content": "Count from 1 to 10, one per line. After 5, write END.",
        }
    ],
)
print(f"text:\n{r3.content[0].text}")
print(f"\nstop_reason  : {r3.stop_reason}")
print(f"stop_sequence: {r3.stop_sequence!r}  <-- which one fired")


# ============================================================
#  4) refusal — covered conceptually
# ============================================================
section("stop_reason: refusal (not triggered here)")
print("""\
When Claude declines a request on safety grounds, stop_reason='refusal' and
response.stop_details carries structured info:

  if response.stop_reason == 'refusal' and response.stop_details:
      print(response.stop_details.category)     # e.g. 'cyber', 'bio', None
      print(response.stop_details.explanation)  # human-readable reason

Treat refusals as terminal — don't retry the same prompt.
""")


# ============================================================
#  5) tool_use and pause_turn — covered in 07_tool_use_manual.py
# ============================================================
section("stop_reason: tool_use / pause_turn")
print("""\
tool_use   — the model emitted a tool_use block and is waiting for your
             tool_result. See 07_tool_use_manual.py for the loop.
pause_turn — a server-side tool (web_search, code_execution) hit its built-in
             iteration limit (default 10). Re-send the assistant turn back to
             continue automatically. Set a max_continuations counter to avoid
             infinite loops.
""")
