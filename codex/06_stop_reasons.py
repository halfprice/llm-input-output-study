"""
06_stop_reasons.py — every termination state on the Responses API.

OpenAI's Responses API uses TWO complementary fields:
  response.status              — top-level outcome of the whole call
  response.incomplete_details  — populated when status='incomplete', with .reason

Status values:
  completed   — normal finish (≈ Anthropic's end_turn)
  incomplete  — the call ran out of budget. incomplete_details.reason ∈
                  "max_output_tokens"          — hit max_output_tokens
                  "content_filter"             — output was filtered
                  "max_tool_calls"             — exceeded max_tool_calls budget
                  "context_window_exceeded"    — context window filled up
  failed      — server-side error (see response.error)
  in_progress — only seen while streaming

Per-output-item status (for message items):
  output[i].status ∈ "completed" | "incomplete" | "in_progress"

There is NO custom `stop_sequences` on the Responses API like Anthropic has.
Use prompt engineering or stop_sequences via Chat Completions if you need it.

Tool-use signal:
  When the model wants a tool, the response contains a `function_call`
  output item. Status is still `completed` for that response, but you'll
  see the function_call instead of a message. See script 07.
"""
from _common import client, MODEL, section


# ============================================================
#  1) status: 'completed' — normal completion
# ============================================================
section("status: completed")
r1 = client.responses.create(
    model=MODEL,
    input="Say hello in 5 words.",
    reasoning={"effort": "none"},   # gpt-5.6: "minimal" was removed, use "none"
)
print(f"output_text         : {r1.output_text!r}")
print(f"status              : {r1.status}")
print(f"incomplete_details  : {r1.incomplete_details}")


# ============================================================
#  2) status: 'incomplete' (max_output_tokens hit)
# ============================================================
# Cap max_output_tokens low enough that we run out mid-response.
# Note: when reasoning is on, the cap covers reasoning + output text both.
# To get visible truncation, use effort='none' so the whole budget is text.
section("status: incomplete (max_output_tokens)")
r2 = client.responses.create(
    model=MODEL,
    max_output_tokens=20,                 # deliberately tiny
    input="Explain the Internet Protocol in full detail.",
    reasoning={"effort": "none"},   # gpt-5.6: "minimal" was removed, use "none"
)
print(f"output_text         : {r2.output_text!r}  <-- may be empty if reasoning consumed the budget")
print(f"status              : {r2.status}")
print(f"incomplete_details  : {r2.incomplete_details}")
print(f"reasoning_tokens    : {r2.usage.output_tokens_details.reasoning_tokens}")
print(f"output_tokens       : {r2.usage.output_tokens}")


# ============================================================
#  3) Other status values (conceptual)
# ============================================================
section("Other status values")
print("""\
failed          — response.error has {code, message}
                  e.g. 'rate_limit_exceeded', 'invalid_api_key'

in_progress     — only visible while streaming; the final 'response.completed'
                  event carries the terminal status

content_filter  — OpenAI's safety filter blocked some output. The .reason
                  in incomplete_details will say 'content_filter'.

max_tool_calls  — you set max_tool_calls to bound agentic loops, and the
                  model exceeded it before producing a final answer.
""")


# ============================================================
#  4) function_call output items (tool-use signal)
# ============================================================
section("tool-use signal: function_call output items")
print("""\
There is no 'tool_use' stop_reason on the Responses API. Instead, the model
emits a `function_call` item in the output array, and the response status
stays `completed`. To detect it:

  for item in response.output:
      if item.type == 'function_call':
          # model wants to call item.name with item.arguments (JSON string)
          pass

See script 07 for the full loop.
""")
