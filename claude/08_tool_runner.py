"""
08_tool_runner.py — let the SDK drive the loop for you.

The SDK provides a beta `tool_runner` helper that:
  - generates the input_schema from your Python type hints + docstring
  - runs the agentic loop (call model → execute tools → feed results back)
  - yields each intermediate Message so you can observe progress

Compared to 07_tool_use_manual.py:
  - You don't write the loop.
  - You don't write JSON Schema.
  - You don't append tool_result blocks by hand.

Trade-off: less hookable. Use the manual loop (07_) if you need to gate or
log each tool call, do human-in-the-loop approval, or run tools concurrently
with custom dispatching.
"""
import math

from anthropic import beta_tool

from _common import client, MODEL, section, dump


# ============================================================
#  Define tools as plain Python functions
# ============================================================
# `@beta_tool` reads your type hints + docstring to build the JSON Schema.
# The docstring `Args:` block describes each parameter.
@beta_tool
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression. Use this for ANY math.

    Args:
        expression: Python-style arithmetic, e.g. '12 * (3 + 4)' or 'math.sqrt(2)'.
    """
    allowed = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
    try:
        return str(eval(expression, {"__builtins__": {}}, allowed))
    except Exception as e:
        return f"ERROR: {e}"


@beta_tool
def get_capital(country: str) -> str:
    """Look up the capital city of a country.

    Args:
        country: Country name in English.
    """
    table = {"france": "Paris", "japan": "Tokyo", "kenya": "Nairobi"}
    return table.get(country.lower(), f"Unknown country: {country}")


# ============================================================
#  Run the agentic loop with one call
# ============================================================
section("Tool runner — auto-loop")

runner = client.beta.messages.tool_runner(
    model=MODEL,
    max_tokens=1024,
    tools=[calculator, get_capital],
    messages=[
        {
            "role": "user",
            "content": (
                "What is the capital of Kenya, and what is sqrt(2) to 5 decimal places?"
            ),
        }
    ],
)

# Iterate to see each step. `runner` yields a BetaMessage per call to /v1/messages,
# including the final non-tool-use message that ends the loop.
for i, message in enumerate(runner, start=1):
    print(f"\n--- runner step {i} ---")
    print(f"stop_reason: {message.stop_reason}")
    for block in message.content:
        if block.type == "text":
            print(f"  text       : {block.text!r}")
        elif block.type == "tool_use":
            print(f"  tool_use   : {block.name}({block.input})")
        elif block.type == "thinking":
            print(f"  thinking   : {block.thinking[:80]!r}...")

# After iteration, the final message is also accessible:
section("FINAL MESSAGE")
final = message  # last value from the loop
final_text = next((b.text for b in final.content if b.type == "text"), "")
print(final_text)
dump(final.usage, "final usage")


# ============================================================
#  Notes
# ============================================================
section("NOTES")
print("""\
• The tool runner is currently a BETA feature. Import from `anthropic` and
  use `client.beta.messages.tool_runner(...)`.
• Schemas are derived from type hints — supported types include str, int,
  float, bool, list[T], dict, enum.Enum, and Pydantic models.
• Use @beta_async_tool with async def functions for async dispatch.
• For MCP (Model Context Protocol) servers, the SDK provides helpers in
  `anthropic.lib.tools.mcp` to convert MCP tools to runner-compatible tools.
""")
