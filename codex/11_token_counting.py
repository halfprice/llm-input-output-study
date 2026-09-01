"""
11_token_counting.py — measure tokens locally with tiktoken.

OpenAI has NO equivalent of Anthropic's /v1/messages/count_tokens endpoint.
Instead, you count locally with the `tiktoken` library (open-source, by
OpenAI). It's offline, fast, and free — but a rough estimate for some
modern models because the per-message overhead is encoder-dependent.

Concepts:
  - Each model uses a specific encoder (e.g. gpt-5 → "o200k_base").
  - `tiktoken.encoding_for_model(name)` returns the right encoder.
  - For chat-style inputs, every message adds a few constant tokens of
    overhead (role tokens, separators). The exact count is documented per
    model family.

Use cases:
  - Estimate input cost before sending.
  - Decide whether to compact long conversations.
  - Audit a prefix you THINK is stable for caching.
"""
import tiktoken

from _common import MODEL, section


# ============================================================
#  Encoder selection
# ============================================================
section("encoder for the model")
try:
    enc = tiktoken.encoding_for_model(MODEL)
except KeyError:
    # Newer models may not be in tiktoken's known list yet. Fall back to
    # the encoder used by the gpt-4o / gpt-5 families.
    enc = tiktoken.get_encoding("o200k_base")
print(f"model            : {MODEL}")
print(f"encoder name     : {enc.name}")


# ============================================================
#  Count tokens in a raw string
# ============================================================
section("raw string")
text = "Hello!"
ids = enc.encode(text)
print(f"text   : {text!r}")
print(f"tokens : {ids}")
print(f"count  : {len(ids)}")


# ============================================================
#  Count tokens for a chat-style input (rough)
# ============================================================
# Approximation for the Responses API: add ~4 tokens per message (role and
# separator overhead). For exact counts, send the request and read
# response.usage.input_tokens.
section("chat-style input (approximation)")

instructions = "You are a careful shopping assistant."
input_messages = [
    {"role": "user", "content": "Do you have any blue ergonomic chairs under $300?"},
]


def count_chat(instructions: str, messages: list[dict]) -> int:
    total = len(enc.encode(instructions or "")) + 4   # system overhead
    for m in messages:
        total += len(enc.encode(m["content"])) + 4    # per-message overhead
    return total


approx = count_chat(instructions, input_messages)
print(f"approx input tokens : {approx}")


# ============================================================
#  Exact counts only come from a real request
# ============================================================
section("exact count via a real request")
from _common import client

resp = client.responses.create(
    model=MODEL,
    instructions=instructions,
    input=input_messages,
    reasoning={"effort": "none"},   # gpt-5.6: "minimal" was removed, use "none"
)
print(f"actual input_tokens : {resp.usage.input_tokens}")
print(f"actual output_tokens: {resp.usage.output_tokens}")
print(f"approx vs actual    : approx={approx}, actual={resp.usage.input_tokens}")


# ============================================================
#  Cost estimation
# ============================================================
section("cost estimate")
# Approximate Opus 4.8 / gpt-5-family pricing for comparison (verify on the
# provider's pricing page; these numbers may have moved):
PRICE_PER_INPUT_TOKEN_USD = 1.25 / 1_000_000   # gpt-5 list input price ($1.25/1M); gpt-5.6-sol pricing not published via API — check the pricing page
estimated_cost = resp.usage.input_tokens * PRICE_PER_INPUT_TOKEN_USD
print(f"estimated input cost : ${estimated_cost:.6f}")
print("Output tokens (including reasoning) are billed separately — typically")
print("~10× input price for reasoning-class models.")
