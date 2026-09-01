"""
12_gpt56_new_features.py — what gpt-5.6 added on top of gpt-5.

Everything here was discovered by probing gpt-5.6-sol live (bad values in a
request make the API list the accepted ones in the error message). Scripts
01–11 are the "same shape as before" tour; this one is the delta.

New RESPONSE fields:
  message.phase                          "commentary" | "final_answer"
  usage.input_tokens_details.cache_write_tokens
  usage.compute_units                    (null on standard tier)
  response.prompt_cache_retention        "24h" by default now
  response.reasoning.{mode, context}     (see script 05)
  response.tool_usage                    per-hosted-tool counters
  response.billing.payer                 "developer"

New REQUEST knobs:
  text.verbosity           low | medium | high
  service_tier             auto | default | fast | flex | priority
  reasoning.effort         none / xhigh / max (script 05)
  reasoning.mode / context (script 05)

New TOOL types (tools[].type):
  custom                   — freeform text args instead of JSON
  shell                    — model emits shell_call; you run it, return shell_call_output
  apply_patch              — model emits apply_patch_call with a diff
  tool_search + defer_loading — lazy tool loading for big tool catalogs
  namespace                — group function tools under a name
  programmatic_tool_calling — model writes a small program that calls your tools
  (plus hosted: code_interpreter, file_search, web_search_preview, image_generation,
   mcp, computer / computer_use_preview — unchanged from gpt-5)

Removed:
  reasoning.effort = "minimal"   → 400 unsupported_value. Use "none".
  temperature                    → 400 unsupported_parameter.

Run:  .venv/bin/python codex/12_gpt56_new_features.py
"""
import json

from _common import client, MODEL, section, dump

WEATHER_TOOL = {
    "type": "function",
    "name": "get_weather",
    "description": "Get current temperature (celsius) for a city.",
    "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
        "additionalProperties": False,
    },
    "strict": True,
}


def item_summary(item):
    """One-line description of any output item, tolerant of unknown types."""
    d = item.model_dump()
    keep = {k: d[k] for k in ("type", "phase", "name", "arguments", "input",
                              "code", "action", "operation", "namespace", "status")
            if d.get(k) is not None}
    if item.type == "message":
        keep["text"] = item.content[0].text[:90]
    if item.type == "tool_search_output":
        keep["tools"] = [t["name"] for t in d.get("tools", [])]
    return keep


# ============================================================
#  1) message.phase — commentary vs final_answer
# ============================================================
# When the model talks *before* calling a tool (a preamble), that message is
# tagged phase="commentary". The message that ends the turn is
# phase="final_answer". Useful for UIs that render preambles differently.
section("1) message.phase")
r = client.responses.create(
    model=MODEL,
    instructions="Before calling any tool, tell the user in one sentence what you are about to do.",
    input="What is the weather in Tokyo? Use the tool.",
    tools=[WEATHER_TOOL],
)
for it in r.output:
    print(" ", json.dumps(item_summary(it)))

r2 = client.responses.create(model=MODEL, input="Say hi.", reasoning={"effort": "none"})
print("\nplain answer:", json.dumps(item_summary(r2.output[0])))


# ============================================================
#  2) text.verbosity
# ============================================================
section("2) text.verbosity — same prompt, three lengths")
for v in ["low", "medium", "high"]:
    r = client.responses.create(
        model=MODEL,
        input="Explain what a mutex is.",
        reasoning={"effort": "none"},
        text={"verbosity": v},
    )
    print(f"verbosity={v:6}  output_tokens={r.usage.output_tokens:4}  chars={len(r.output_text)}")


# ============================================================
#  3) usage / caching / billing fields
# ============================================================
section("3) new usage + response fields")
r = client.responses.create(model=MODEL, input="hi", reasoning={"effort": "none"})
dump(r.usage, "usage (note cache_write_tokens, compute_units)")
print(f"prompt_cache_retention : {r.prompt_cache_retention}")
print(f"service_tier           : {r.service_tier}")
print(f"billing                : {r.billing}")
print(f"tool_usage             : {r.tool_usage}")

section("3b) service_tier='fast'")
r = client.responses.create(model=MODEL, input="hi", reasoning={"effort": "none"}, service_tier="fast")
print(f"requested 'fast' → response.service_tier = {r.service_tier!r}")


# ============================================================
#  4) custom tool — freeform text arguments
# ============================================================
# No JSON schema. The model passes a raw string on `.input`. Ideal for
# shell commands, SQL, DSLs, where JSON-escaping is a nuisance.
section("4) tools[].type='custom' → custom_tool_call")
r = client.responses.create(
    model=MODEL,
    input="Write a bash one-liner that lists files by size. Call the run_bash tool with it.",
    tools=[{"type": "custom", "name": "run_bash",
            "description": "Runs a raw bash command string. Pass the raw command text, not JSON."}],
)
for it in r.output:
    print(" ", json.dumps(item_summary(it)))
print("  → reply with {'type': 'custom_tool_call_output', 'call_id': ..., 'output': '...'}")


# ============================================================
#  5) shell tool — model emits shell_call
# ============================================================
section("5) tools[].type='shell' → shell_call")
r = client.responses.create(
    model=MODEL,
    input="List files in the current directory.",
    tools=[{"type": "shell"}],
)
for it in r.output:
    print(" ", json.dumps(item_summary(it)))
print("  → run action.commands yourself, reply with shell_call_output")


# ============================================================
#  6) apply_patch tool — model emits a diff
# ============================================================
section("6) tools[].type='apply_patch' → apply_patch_call")
r = client.responses.create(
    model=MODEL,
    input="Create a file hello.txt containing the single line: hi",
    tools=[{"type": "apply_patch"}],
)
for it in r.output:
    print(" ", json.dumps(item_summary(it)))
print("  → apply the operation.diff yourself, reply with apply_patch_call_output")


# ============================================================
#  7) tool_search + defer_loading — lazy tool catalogs
# ============================================================
# Mark tools defer_loading=True and add a tool_search tool. The model first
# emits tool_search_call, the server answers with tool_search_output (the
# full definitions of the matched tools), THEN the model calls them.
section("7) tools[].type='tool_search' + defer_loading")
stock_tool = {**WEATHER_TOOL, "name": "get_stock", "description": "Get a stock price.",
              "parameters": {"type": "object", "properties": {"ticker": {"type": "string"}},
                             "required": ["ticker"], "additionalProperties": False}}
r = client.responses.create(
    model=MODEL,
    input="What is the weather in Tokyo? Use a tool.",
    tools=[{"type": "tool_search"},
           {**WEATHER_TOOL, "defer_loading": True},
           {**stock_tool, "defer_loading": True}],
)
for it in r.output:
    print(" ", json.dumps(item_summary(it)))


# ============================================================
#  8) namespace — group tools
# ============================================================
section("8) tools[].type='namespace'")
r = client.responses.create(
    model=MODEL,
    input="What is the weather in Tokyo? Use a tool.",
    tools=[{"type": "namespace", "name": "weather_ns", "description": "Weather tools",
            "tools": [WEATHER_TOOL]}],
)
for it in r.output:
    print(" ", json.dumps(item_summary(it)))
print("  → function_call now carries .namespace")


# ============================================================
#  9) programmatic_tool_calling — model writes code that calls tools
# ============================================================
# Give the function tool allowed_callers=["programmatic"]. The model emits a
# `program` item (JS-like code calling tools.<name>) and then the individual
# function_call items the program triggers. You still execute each
# function_call and return function_call_output; the runtime resumes the
# program. Without allowed_callers, this degrades to ordinary parallel calls.
section("9) tools[].type='programmatic_tool_calling' → program item")
r = client.responses.create(
    model=MODEL,
    input="Get the weather for Tokyo, Paris and Lima and tell me the warmest. Use the tools.",
    tools=[{"type": "programmatic_tool_calling"},
           {**WEATHER_TOOL, "allowed_callers": ["programmatic"]}],
)
for it in r.output:
    print(" ", json.dumps(item_summary(it)))


# ============================================================
#  10) Removed things — confirm the errors
# ============================================================
section("10) removed: effort='minimal', temperature")
import openai
for kwargs in ({"reasoning": {"effort": "minimal"}}, {"temperature": 0.5}):
    try:
        client.responses.create(model=MODEL, input="hi", **kwargs)
    except openai.BadRequestError as e:
        print(f"  {list(kwargs)[0]:12} → {e.body['message']}")
