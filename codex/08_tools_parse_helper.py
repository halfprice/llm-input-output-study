"""
08_tools_parse_helper.py — Pydantic-typed tool arguments via `responses.parse`.

OpenAI's SDK doesn't ship a full "tool runner" auto-loop like Anthropic's
@beta_tool decorator. The closest equivalents are:

  1. `client.responses.parse(...)`     — Pydantic-typed structured output
                                          AND Pydantic-typed tool arguments
                                          (the model fills in your dataclass)
  2. `pydantic_function_tool(MyClass)` — convert a Pydantic class into a
                                          tool definition with strict mode

You still write the loop yourself, but you don't write JSON Schema and the
arguments arrive as typed Pydantic instances instead of JSON strings.

In production, picking between the manual loop (07) and this helper is
about: do you want typed argument validation? If yes → parse. If you need
more control (logging hooks, human approval, custom dispatch) → manual.
"""
import math
import json
from typing import Literal

from pydantic import BaseModel, Field
from openai import pydantic_function_tool

from _common import client, MODEL, section


# ============================================================
#  Define tools as Pydantic argument models
# ============================================================
# The class docstring becomes the tool description; field descriptions
# carry into the JSON Schema; field types drive validation.
class Calculator(BaseModel):
    """Evaluate a basic arithmetic expression. Use this for any math."""
    expression: str = Field(..., description="Python-style arithmetic, e.g. '2 ** 0.5'.")


class GetCapital(BaseModel):
    """Look up the capital city of a country."""
    country: str = Field(..., description="Country name in English.")


TOOLS = [
    pydantic_function_tool(Calculator),
    pydantic_function_tool(GetCapital),
]
# Each result is a dict with type='function', name=<class name>, strict=True,
# and parameters=<JSON Schema auto-derived from the Pydantic model>.


# ============================================================
#  Tool implementations
# ============================================================
def run_calculator(args: Calculator) -> str:
    allowed = {n: getattr(math, n) for n in dir(math) if not n.startswith("_")}
    try:
        return str(eval(args.expression, {"__builtins__": {}}, allowed))
    except Exception as e:
        return f"ERROR: {e}"


def run_get_capital(args: GetCapital) -> str:
    table = {"france": "Paris", "japan": "Tokyo", "kenya": "Nairobi"}
    return table.get(args.country.lower(), f"Unknown country: {args.country}")


# ============================================================
#  Agentic loop with parse() — arguments arrive parsed
# ============================================================
section("REQUEST")

resp = client.responses.parse(
    model=MODEL,
    input="What is the capital of Kenya, and what is sqrt(2) to 5 decimal places?",
    tools=TOOLS,
)

turn = 1
while True:
    print(f"\n--- Turn {turn} ---")
    print(f"status            : {resp.status}")
    print(f"output item types : {[i.type for i in resp.output]}")

    function_calls = [i for i in resp.output if i.type == "function_call"]
    if not function_calls:
        break

    outputs = []
    for fc in function_calls:
        # `fc.parsed_arguments` is a Pydantic instance built from `fc.arguments`.
        # parse() handled the json.loads + validation for us.
        parsed = fc.parsed_arguments
        if isinstance(parsed, Calculator):
            result = run_calculator(parsed)
        elif isinstance(parsed, GetCapital):
            result = run_get_capital(parsed)
        else:
            result = f"Unknown tool: {fc.name}"

        print(f"  function_call → {fc.name}({parsed!r}) → {result!r}")
        outputs.append({
            "type":    "function_call_output",
            "call_id": fc.call_id,
            "output":  result,
        })

    turn += 1
    resp = client.responses.parse(
        model=MODEL,
        previous_response_id=resp.id,
        input=outputs,
        tools=TOOLS,
    )

    if turn > 8:
        break


# ============================================================
#  Final answer
# ============================================================
section("FINAL ANSWER")
print(resp.output_text)


# ============================================================
#  Notes
# ============================================================
section("NOTES")
print("""\
Differences vs codex/07_tool_use_manual.py:
  • TOOLS is built via pydantic_function_tool() — no hand-written JSON Schema.
  • Function-call arguments arrive as `fc.parsed_arguments` (Pydantic instance),
    not a JSON string — no json.loads needed.
  • Set strict=True on the tool definition to enforce the schema strictly
    (default for pydantic_function_tool).

OpenAI doesn't (yet) provide a single-call auto-loop like Anthropic's
@beta_tool. If you want one:
  - Write a small loop around `client.responses.parse` (10 lines).
  - Or use the OpenAI Agents SDK (`pip install openai-agents`) which adds a
    higher-level Agent abstraction that runs the loop for you.
""")
