"""
09_structured_output.py — force the response to a JSON schema.

Concepts:
  REQUEST  :
    text = {
        "format": {
            "type":   "json_schema",
            "name":   "<schema name>",
            "schema": { ...JSON Schema... },
            "strict": True,
        }
    }
    Note: in the Responses API, structured-output config lives under
    `text.format`, NOT a top-level `response_format` like Chat Completions.

  Pydantic helper (recommended):
    client.responses.parse(..., text_format=MyPydanticClass)
    Returns a response where .output_parsed is your typed instance.

  Schema rules (same as OpenAI Chat Completions):
    - All objects must have `additionalProperties: false`
    - All properties must be listed in `required` (use nullable for optional)
    - Limited subset of JSON Schema — no min/max, regex patterns, etc.
"""
from typing import Literal

from pydantic import BaseModel, Field

from _common import client, MODEL, section


# ============================================================
#  Option A — Pydantic (recommended)
# ============================================================
section("Pydantic-typed structured output")


class LineItem(BaseModel):
    description: str = Field(description="Short name of the item")
    quantity: int
    unit_price_usd: float


class Invoice(BaseModel):
    invoice_number: str
    customer: str
    items: list[LineItem]
    total_usd: float
    payment_terms: Literal["net_15", "net_30", "due_on_receipt"]


resp = client.responses.parse(
    model=MODEL,
    input=(
        "Extract a structured invoice from this email:\n\n"
        "Hey, here's invoice #A-2391 for Acme Coyote Supplies. "
        "We sent over 12 rocket sleds at $499 each and 200 lbs of "
        "birdseed at $2.50/lb. Total comes to $6,488. Net 30 terms.\n"
    ),
    text_format=Invoice,
)

# `output_parsed` is the typed Pydantic instance.
invoice = resp.output_parsed
print(f"type(resp.output_parsed) = {type(invoice).__name__}")
print(f"invoice.invoice_number   = {invoice.invoice_number!r}")
print(f"invoice.customer         = {invoice.customer!r}")
print(f"invoice.total_usd        = {invoice.total_usd}")
print(f"invoice.payment_terms    = {invoice.payment_terms!r}")
print("invoice.items:")
for item in invoice.items:
    print(f"  - {item.quantity:>3} x {item.description!r} @ ${item.unit_price_usd}")

# The raw JSON is still in the response as a message item with output_text.
print(f"\nRaw output_text:\n{resp.output_text}")


# ============================================================
#  Option B — raw JSON schema via text.format
# ============================================================
section("Raw JSON Schema via text.format")

schema = {
    "type": "object",
    "properties": {
        "sentiment":  {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "confidence": {"type": "number"},
        "keywords":   {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sentiment", "confidence", "keywords"],
    "additionalProperties": False,
}

resp2 = client.responses.create(
    model=MODEL,
    input="Classify: 'I waited 45 minutes for a cold coffee. Never again.'",
    text={
        "format": {
            "type":   "json_schema",
            "name":   "sentiment_classification",
            "schema": schema,
            "strict": True,
        }
    },
)

import json
parsed = json.loads(resp2.output_text)
print(f"sentiment  : {parsed['sentiment']!r}")
print(f"confidence : {parsed['confidence']}")
print(f"keywords   : {parsed['keywords']}")


# ============================================================
#  Schema rules
# ============================================================
section("Schema rules to remember")
print("""\
- Top-level type MUST be 'object'.
- Every object MUST have additionalProperties: false.
- Every property MUST be listed in `required`. To make a field optional,
  use {"type": ["string", "null"]} and accept null in your code.
- No JSON Schema features for value constraints (min, max, regex, length).
- Up to 5 levels of nesting; up to 100 total properties across a schema.

Compare to Anthropic:
  - Same shape (json_schema with a strict schema).
  - Anthropic uses output_config.format; OpenAI uses text.format.
  - OpenAI's `strict: True` is more pervasive (also applies to tool inputs).
""")
