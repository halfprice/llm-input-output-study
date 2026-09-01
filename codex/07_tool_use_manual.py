"""
07_tool_use_manual.py — function calling, manual agentic loop.

Concepts:
  REQUEST :
    tools[] — list of tool definitions. Responses API uses a FLAT shape
              (no nested `function: {...}` wrapper from Chat Completions):
                {
                  "type":        "function",
                  "name":        "get_weather",
                  "description": "...",
                  "parameters":  { ...JSON Schema... },
                  "strict":      False,           # optional — schema enforced
                }
    tool_choice — "auto" (default) | "required" | "none"
                  | {"type": "function", "name": "<tool_name>"}

  RESPONSE :
    function_call items in response.output[]:
      {
        "type":      "function_call",
        "id":        "fc_...",                    # opaque
        "call_id":   "call_...",                  # IMPORTANT — echoed in your reply
        "name":      "get_weather",
        "arguments": "{\\"city\\":\\"Tokyo\\"}",  # JSON STRING, not parsed
      }

  Your reply:
    Append `function_call_output` items to the input array on the next call:
      {
        "type":    "function_call_output",
        "call_id": "<the call_id from above>",
        "output":  "result string",
      }
    AND echo back the original function_call item (or use previous_response_id).

Critical differences vs Anthropic:
  - id matching: Anthropic uses `tool_use.id` ↔ `tool_result.tool_use_id`.
    OpenAI uses `function_call.call_id` ↔ `function_call_output.call_id`
    (NOT the `id` field — that's the item ID, different thing).
  - arguments are a JSON STRING, not a parsed object. You must json.loads() it.
  - When using previous_response_id, you only send the new function_call_output
    items — no need to echo the function_call back. Stateful = simpler.
"""
import json
import math

from _common import client, MODEL, section, dump


# ============================================================
#  Define tools
# ============================================================
TOOLS = [
    {
        "type": "function",
        "name": "calculator",
        "description": "Evaluate a basic arithmetic expression. Use this for any math.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Python-style arithmetic, e.g. '2 ** 0.5' or 'math.sqrt(2)'.",
                }
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_capital",
        "description": "Look up the capital city of a country.",
        "parameters": {
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "Country name in English."}
            },
            "required": ["country"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


# ============================================================
#  Tool implementations (YOUR code; OpenAI doesn't run it)
# ============================================================
def run_calculator(expression: str) -> str:
    allowed = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
    try:
        return str(eval(expression, {"__builtins__": {}}, allowed))
    except Exception as e:
        return f"ERROR: {e}"


def run_get_capital(country: str) -> str:
    table = {"france": "Paris", "japan": "Tokyo", "kenya": "Nairobi"}
    return table.get(country.lower(), f"Unknown country: {country}")


def dispatch(name: str, args_json: str) -> str:
    args = json.loads(args_json)       # <-- arguments arrive as a JSON STRING
    if name == "calculator":
        return run_calculator(**args)
    if name == "get_capital":
        return run_get_capital(**args)
    return f"Unknown tool: {name}"


# ============================================================
#  Stateful agentic loop using previous_response_id
# ============================================================
# This is the idiomatic OpenAI pattern: chain calls by referencing the prior
# response, and only send the new function_call_output items each turn.
section("REQUEST")
INITIAL_INPUT = (
    "What is the capital of Japan, and what is sqrt(2) to 5 decimal places? "
    "Use your tools."
)

# Turn 1 — kickoff
resp = client.responses.create(
    model=MODEL,
    input=INITIAL_INPUT,
    tools=TOOLS,
)
print(f"\n--- Turn 1 ---")
print(f"status            : {resp.status}")
print(f"output item types : {[i.type for i in resp.output]}")

turn = 1
while True:
    # Collect any function_call items the model emitted.
    function_calls = [i for i in resp.output if i.type == "function_call"]

    # If there are none, the model produced its final answer. Done.
    if not function_calls:
        break

    # Otherwise execute every call and build function_call_output items.
    outputs = []
    for fc in function_calls:
        result = dispatch(fc.name, fc.arguments)
        print(f"  function_call → {fc.name}({fc.arguments}) → {result!r}")
        outputs.append(
            {
                "type":    "function_call_output",
                "call_id": fc.call_id,        # MUST match — not fc.id
                "output":  result,
            }
        )

    # Next turn — chain via previous_response_id, send ONLY the new outputs.
    turn += 1
    print(f"\n--- Turn {turn} ---")
    resp = client.responses.create(
        model=MODEL,
        previous_response_id=resp.id,
        input=outputs,
        tools=TOOLS,
    )
    print(f"status            : {resp.status}")
    print(f"output item types : {[i.type for i in resp.output]}")

    if turn > 8:                              # safety cap
        print("Too many turns — bailing.")
        break


# ============================================================
#  Final answer
# ============================================================
section("FINAL ANSWER")
print(resp.output_text)


# ============================================================
#  Wire-level details
# ============================================================
section("WIRE-LEVEL DETAILS")
print(f"""\
Final response.id          : {resp.id}
Final status               : {resp.status}
Cumulative chain length    : {turn} turn(s)

Notice what we DIDN'T do (compared with Anthropic):
  - We did NOT resend the original user input every turn.
  - We did NOT echo the assistant's function_call items back manually.
  - We just chained previous_response_id and posted the function_call_output(s).

If you wanted stateless behaviour (no server-side storage of past turns),
set store=False on every call and resend the full input[] array yourself,
including the function_call items echoed back from the prior response.
""")
