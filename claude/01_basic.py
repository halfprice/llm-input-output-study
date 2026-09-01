"""
01_basic.py — the smallest possible request, dissected.

Concepts:
  REQUEST shape  : model, max_tokens, messages (list of {role, content})
  RESPONSE shape : id, type, role, model, content[], stop_reason, usage

The Messages API is a single endpoint: POST /v1/messages.
Everything else in this study (tools, thinking, streaming, caching) is just
extra fields layered on top of this same shape.

Run:  .venv/bin/python 01_basic.py
"""
from _common import client, MODEL, section, dump


# ============================================================
#  REQUEST
# ============================================================
# Required fields:
#   model       — which Claude model to call. Exact string, no aliases.
#   max_tokens  — hard ceiling on output tokens. The model can't see this
#                 value; if it hits the limit mid-thought, stop_reason will
#                 be "max_tokens" and you'll get truncated output.
#   messages    — list of turns. Each turn has a role ("user" or "assistant")
#                 and content (string OR list of content blocks).
#                 First turn MUST be "user".
section("REQUEST")
request = {
    "model": MODEL,
    "max_tokens": 256,
    "messages": [
        {"role": "user", "content": "In one sentence: what does the LLM Messages API return?"},
    ],
}
dump(request, "request payload")


# ============================================================
#  RESPONSE
# ============================================================
response = client.messages.create(**request)
dump(response, "full response object")


# ============================================================
#  KEY FIELDS — what each one means
# ============================================================
section("KEY FIELDS")
print(f"id            : {response.id}             # unique message ID, log this for support tickets")
print(f"type          : {response.type}                          # always 'message' for /v1/messages")
print(f"role          : {response.role}                        # always 'assistant' (the model's turn)")
print(f"model         : {response.model}             # echoes which model actually served the request")
print(f"stop_reason   : {response.stop_reason}                       # why generation stopped — see 06_stop_reasons.py")
print(f"stop_sequence : {response.stop_sequence}                          # which custom stop string was hit (None if not used)")

# usage tracks billing. cache_* fields populate when prompt caching is used.
u = response.usage
print(f"\nusage.input_tokens                   : {u.input_tokens}    # uncached input tokens (full price)")
print(f"usage.output_tokens                  : {u.output_tokens}    # generated tokens")
print(f"usage.cache_creation_input_tokens    : {u.cache_creation_input_tokens}   # written to cache (~1.25x)")
print(f"usage.cache_read_input_tokens        : {u.cache_read_input_tokens}   # served from cache (~0.1x)")


# ============================================================
#  CONTENT BLOCKS — response.content is ALWAYS a list
# ============================================================
# Even simple text responses come as a list. Each block has a .type and
# variant-specific fields. Common types:
#   text             — block.text             (plain output)
#   thinking         — block.thinking         (reasoning trace, see 05_)
#   tool_use         — block.name, block.input (function call, see 07_)
#   server_tool_use  — Anthropic-side tool invocations
section("CONTENT BLOCKS")
for i, block in enumerate(response.content):
    print(f"\ncontent[{i}].type = {block.type!r}")
    if block.type == "text":
        print(f"content[{i}].text = {block.text!r}")
