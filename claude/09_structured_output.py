"""
09_structured_output.py — force the output to match a schema.

Concepts:
  REQUEST  :
    output_config = {
        "format": {
            "type":   "json_schema",
            "schema": { ... JSON Schema ... },
        }
    }
    The model is constrained to emit JSON that validates against `schema`.
    First text block in the response will be a JSON string conforming to it.

  Pydantic helper:
    client.messages.parse(..., output_format=YourBaseModel)
    Returns a Message with a typed `.parsed_output` attribute (your model
    instance), built from a Pydantic class — no hand-written schema.

JSON Schema restrictions:
  - All objects must have additionalProperties=false
  - No min/max/length constraints (SDK strips these client-side)
  - No recursive schemas
  - Cannot combine with citations or assistant prefills
"""
from typing import Literal

from pydantic import BaseModel, Field

from _common import client, MODEL, section, dump


# ============================================================
#  Option A — Pydantic (recommended)
# ============================================================
# Define what you want as a Pydantic model. The SDK turns it into a JSON
# Schema, sends it as output_config, then parses the response back into your
# model instance — typed end to end.
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


resp = client.messages.parse(
    model=MODEL,
    max_tokens=1024,
    output_format=Invoice,
    messages=[
        {
            "role": "user",
            "content": (
                "Extract a structured invoice from this email:\n\n"
                "Hey, here's invoice #A-2391 for Acme Coyote Supplies. "
                "We sent over 12 rocket sleds at $499 each and 200 lbs of "
                "birdseed at $2.50/lb. Total comes to $6,488. Net 30 terms.\n"
            ),
        }
    ],
)

print(f"type(resp.parsed_output) = {type(resp.parsed_output).__name__}")
invoice: Invoice = resp.parsed_output
print(f"invoice.invoice_number   = {invoice.invoice_number!r}")
print(f"invoice.customer         = {invoice.customer!r}")
print(f"invoice.total_usd        = {invoice.total_usd}")
print(f"invoice.payment_terms    = {invoice.payment_terms!r}")
print("invoice.items:")
for item in invoice.items:
    print(f"  - {item.quantity:>3} x {item.description!r} @ ${item.unit_price_usd}")

# The raw JSON that the model produced is still in resp.content as a text block.
print(f"\nRaw JSON text:\n{resp.content[0].text}")


# ============================================================
#  Option B — raw JSON Schema (when not using Pydantic)
# ============================================================
section("Raw JSON Schema via output_config")

schema = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "confidence": {"type": "number"},
        "keywords":   {"type": "array",  "items": {"type": "string"}},
    },
    "required": ["sentiment", "confidence", "keywords"],
    "additionalProperties": False,
}

resp2 = client.messages.create(
    model=MODEL,
    max_tokens=512,
    output_config={"format": {"type": "json_schema", "schema": schema}},
    messages=[
        {"role": "user", "content": "Classify: 'I waited 45 minutes for a cold coffee. Never again.'"}
    ],
)

import json
text = next(b.text for b in resp2.content if b.type == "text")
parsed = json.loads(text)
print(f"sentiment  : {parsed['sentiment']!r}")
print(f"confidence : {parsed['confidence']}")
print(f"keywords   : {parsed['keywords']}")


# ============================================================
#  Strict tool inputs — same idea, applied to tool calls
# ============================================================
section("Strict tool inputs (related feature)")
print("""\
Setting `strict: true` on a tool definition forces tool inputs to validate
against the input_schema. Same JSON Schema restrictions apply. Example:

  tools=[{
      "name": "book_flight",
      "description": "...",
      "strict": True,                 # <-- the new bit
      "input_schema": {
          "type": "object",
          "properties": {...},
          "required": [...],
          "additionalProperties": False,
      },
  }]
""")
