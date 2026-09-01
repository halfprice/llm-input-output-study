"""
07_tool_use_manual.py — function calling, manual agentic loop.

Concepts:
  REQUEST  :
    tools[]      — list of tool definitions, each with name, description,
                   input_schema (JSON Schema). Optional `strict: true` makes
                   the input STRICTLY conform to the schema.
    tool_choice  — {"type": "auto"}                       (default)
                   {"type": "any"}                        (must use SOME tool)
                   {"type": "tool", "name": "calculator"} (force specific tool)
                   {"type": "none"}                       (forbid all tools)
                   Add "disable_parallel_tool_use": true to cap at 1 per turn.

  RESPONSE :
    content[]    — may contain tool_use blocks alongside (or instead of) text:
                     ToolUseBlock(id="toolu_...", name="calc", input={...})
    stop_reason  — "tool_use" when the model wants a tool to run

  Your job:
    1. See stop_reason="tool_use" and tool_use blocks in content.
    2. Execute each tool with its `input`.
    3. Send the assistant's response back verbatim (preserves tool_use blocks
       AND any thinking signatures), THEN a user turn with one tool_result
       per tool_use:
           {"type": "tool_result", "tool_use_id": "toolu_...", "content": "..."}
    4. Loop until stop_reason="end_turn".

  is_error : if a tool failed, set is_error=True on the tool_result and put
             the error message in content. The model can recover (try again,
             different inputs, or apologise).
"""
import math

from _common import client, MODEL, section, dump


# ============================================================
#  Define tools
# ============================================================
# Each tool is a dict with three required keys: name, description, input_schema.
# The description is what the model reads to decide WHEN to call this tool —
# treat it like a docstring written for an LLM.
TOOLS = [
    {
        "name": "calculator",
        "description": "Evaluate a basic arithmetic expression. Use this for any math, even simple addition.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "A Python-style arithmetic expression, e.g. '12 * (3 + 4)' or 'math.sqrt(2)'.",
                }
            },
            "required": ["expression"],
        },
    },
    {
        "name": "get_capital",
        "description": "Look up the capital city of a country.",
        "input_schema": {
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "Country name in English."},
            },
            "required": ["country"],
        },
    },
]


# ============================================================
#  Tool implementations (this is YOUR code — the API doesn't run it)
# ============================================================
def run_calculator(expression: str) -> str:
    # Tiny sandbox — only math.* names are exposed. NEVER use plain eval in
    # production; this is for illustration.
    allowed = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
    try:
        return str(eval(expression, {"__builtins__": {}}, allowed))
    except Exception as e:
        return f"ERROR: {e}"


def run_get_capital(country: str) -> str:
    table = {"france": "Paris", "japan": "Tokyo", "kenya": "Nairobi"}
    return table.get(country.lower(), f"Unknown country: {country}")


def dispatch(name: str, tool_input: dict) -> tuple[str, bool]:
    """Returns (result_text, is_error)."""
    if name == "calculator":
        out = run_calculator(**tool_input)
        return out, out.startswith("ERROR")
    if name == "get_capital":
        return run_get_capital(**tool_input), False
    return f"Unknown tool: {name}", True


# ============================================================
#  The agentic loop
# ============================================================
section("REQUEST")
messages = [
    {
        "role": "user",
        "content": (
            "What is the capital of Japan, and what is sqrt(2) to 5 decimal places? "
            "Use your tools."
        ),
    }
]

turn = 0
while True:
    turn += 1
    print(f"\n--- Turn {turn}: calling /v1/messages ---")
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=TOOLS,
        messages=messages,
    )
    print(f"stop_reason: {resp.stop_reason}")

    # Always append the assistant turn back — keeps tool_use blocks and any
    # thinking signatures intact for the next round.
    messages.append({"role": "assistant", "content": resp.content})

    # If the model is done, we're done.
    if resp.stop_reason == "end_turn":
        break

    # Otherwise collect tool_use blocks and run each.
    tool_results = []
    for block in resp.content:
        if block.type == "tool_use":
            print(f"  tool_use → name={block.name!r}, input={block.input!r}, id={block.id!r}")
            result_text, is_error = dispatch(block.name, block.input)
            print(f"           → result={result_text!r} (is_error={is_error})")
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,    # MUST match the tool_use.id
                    "content": result_text,
                    "is_error": is_error,
                }
            )

    # Tool results go back in a USER turn (yes, user — even though they came
    # from your tools, the API treats them as input to the next model call).
    if tool_results:
        messages.append({"role": "user", "content": tool_results})

    # Safety net so a misbehaving loop can't run forever.
    if turn > 8:
        print("Too many turns — bailing out.")
        break


# ============================================================
#  Final reply
# ============================================================
section("FINAL ANSWER")
final_text = next((b.text for b in resp.content if b.type == "text"), "")
print(final_text)

section("FULL MESSAGE HISTORY")
dump(messages)
