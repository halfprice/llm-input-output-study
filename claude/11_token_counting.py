"""
11_token_counting.py — measure before you spend.

Concepts:
  client.messages.count_tokens(...) takes the SAME shape as messages.create
  but doesn't run inference. It returns the input_tokens count that
  messages.create would charge, letting you:
    - estimate cost before sending
    - decide whether to compact a long conversation
    - validate that your "frozen" prompt prefix really is byte-identical
      across requests (caching debug)

  RESPONSE :
    MessageTokensCount(input_tokens=<int>)

Counting input is cheap (a separate endpoint, basically free). Output
tokens you don't know in advance — they depend on what the model generates.
"""
from _common import client, MODEL, section


# ============================================================
#  Count tokens for a small prompt
# ============================================================
section("count_tokens — tiny prompt")
r = client.messages.count_tokens(
    model=MODEL,
    messages=[{"role": "user", "content": "Hello!"}],
)
print(f"input_tokens = {r.input_tokens}")


# ============================================================
#  count_tokens accepts system, messages, tools — full /v1/messages shape
# ============================================================
section("count_tokens — system + messages + tools")

tools = [
    {
        "name": "search_inventory",
        "description": "Search the product inventory.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
]

r2 = client.messages.count_tokens(
    model=MODEL,
    system="You are a careful shopping assistant.",
    tools=tools,
    messages=[
        {"role": "user", "content": "Do you have any blue ergonomic chairs under $300?"}
    ],
)
print(f"input_tokens = {r2.input_tokens}")
print("(notice how adding tools + system pushed the count up vs. the tiny prompt)")


# ============================================================
#  Estimate cost before sending (Opus 4.8 is $5 / 1M input tokens)
# ============================================================
section("cost estimate")
PRICE_PER_TOKEN_USD = 5.00 / 1_000_000
estimated = r2.input_tokens * PRICE_PER_TOKEN_USD
print(f"estimated input cost: ${estimated:.6f}")
print("(plus output tokens at $25/1M, which you can't know until generation runs)")


# ============================================================
#  Use case: detect prefix drift in cached prompts
# ============================================================
section("debugging cache misses with count_tokens")
print("""\
If your cache_read_input_tokens is 0 across repeated requests, run
count_tokens on TWO consecutive prompts:

  c1 = client.messages.count_tokens(model=MODEL, system=sys1, tools=tools1, messages=msgs1)
  c2 = client.messages.count_tokens(model=MODEL, system=sys2, tools=tools2, messages=msgs2)
  print(c1.input_tokens, c2.input_tokens)

If the counts differ for what you think is the SAME prefix, something is
varying — most often:
  • Non-deterministic JSON ordering (json.dumps without sort_keys=True)
  • Hidden timestamps or UUIDs in the system prompt
  • Reordered tools list
""")
