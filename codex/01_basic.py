"""
01_basic.py — minimal Responses API request, dissected.

Concepts:
  REQUEST shape  : model, input  (no max_tokens required)
  RESPONSE shape : id, status, output[], output_text, usage, model

OpenAI's Responses API (POST /v1/responses) is a unified endpoint that
replaced the older Chat Completions for newer models. All concepts in this
study (vision, tools, reasoning, streaming, caching) layer on top of this
same shape.

Big difference vs Anthropic's Messages API:
  - `output` is an ARRAY OF ITEMS, each with a `type` field. You usually
    see a `reasoning` item followed by a `message` item. On gpt-5.6 the
    reasoning item is ADAPTIVE — the model occasionally skips it entirely
    on trivial prompts (0 reasoning_tokens, output[0] is the message).
    Tool calls appear as `function_call` items.
  - There is a convenience `response.output_text` that concatenates all
    message-text content for you — like Anthropic doesn't have.

Run:  .venv/bin/python codex/01_basic.py
"""
from _common import client, MODEL, section, dump


# ============================================================
#  REQUEST
# ============================================================
# Minimum shape:
#   model — the OpenAI model ID. Older aliases like "gpt-5" resolve to a
#           dated snapshot in response.model (e.g. "gpt-5-2025-08-07");
#           "gpt-5.6-sol" is echoed back verbatim (no dated snapshot).
#   input — either a string (treated as a single user message) OR an
#           array of typed input items. We'll use the string form here.
#
# Notice what's NOT required (compare with Anthropic):
#   - No max_tokens — the model picks. Use max_output_tokens to cap it.
#   - No messages array — `input` can be a bare string.
section("REQUEST")
request = {
    "model": MODEL,
    "input": "In one sentence: what does the OpenAI Responses API return?",
}
dump(request, "request payload")


# ============================================================
#  RESPONSE
# ============================================================
response = client.responses.create(**request)
dump(response, "full response object")


# ============================================================
#  KEY FIELDS
# ============================================================
section("KEY FIELDS")
print(f"id             : {response.id}      # unique response ID")
print(f"object         : {response.object}                              # always 'response'")
print(f"model          : {response.model}             # model the API actually used (gpt-5 aliases resolve to dated snapshots)")
print(f"status         : {response.status}                          # 'completed' / 'incomplete' / 'failed' / 'in_progress'")
print(f"created_at     : {response.created_at}                # Unix epoch seconds")
print(f"output_text    : {response.output_text[:80]!r}")
print(f"                 ^ SDK convenience: concatenates text from all message items")


# ============================================================
#  USAGE — billing-relevant counters
# ============================================================
section("USAGE")
u = response.usage
print(f"input_tokens                              : {u.input_tokens}")
print(f"output_tokens                             : {u.output_tokens}")
print(f"total_tokens                              : {u.total_tokens}")
print(f"input_tokens_details.cached_tokens        : {u.input_tokens_details.cached_tokens}")
print(f"output_tokens_details.reasoning_tokens    : {u.output_tokens_details.reasoning_tokens}")
print()
print("Important: reasoning_tokens are BILLED AS OUTPUT TOKENS but reported")
print("separately. On gpt-5 even a 'Hi' prompt consumed ~300 of them; gpt-5.6")
print("is adaptive and may spend 0 on trivial prompts. Use effort='none' to force 0.")


# ============================================================
#  OUTPUT[] — array of typed items
# ============================================================
# Every Responses API call returns `output` as an ARRAY. Each entry has a
# `type`. Common types:
#   reasoning      — model's internal reasoning (summary may be empty
#                    unless you opt in with reasoning={'summary': 'auto'});
#                    may be absent on gpt-5.6 for trivial prompts
#   message        — note the gpt-5.6 `phase` field: 'final_answer' or
#                    'commentary' (a preamble before a tool call, script 12)
#   message        — actual assistant message, with content[] of output_text blocks
#   function_call  — model wants a tool to run (script 07)
section("OUTPUT ITEMS")
for i, item in enumerate(response.output):
    print(f"\noutput[{i}].type = {item.type!r}")
    if item.type == "message":
        for j, block in enumerate(item.content):
            print(f"  content[{j}].type = {block.type!r}")
            if block.type == "output_text":
                print(f"  content[{j}].text = {block.text!r}")
    elif item.type == "reasoning":
        summaries = item.summary or []
        print(f"  summary count: {len(summaries)}  (empty unless reasoning.summary='auto')")
