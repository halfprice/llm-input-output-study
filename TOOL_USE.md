# Tool Use — Deep Dive

A walkthrough of how function calling actually works on the wire: every message, every block, every loop iteration, traced against a real captured run.

The corresponding code is in [`claude/07_tool_use_manual.py`](claude/07_tool_use_manual.py) (manual loop) and [`claude/08_tool_runner.py`](claude/08_tool_runner.py) (SDK auto-loop).

---

## Mental model

The Messages API is **stateless**. Every call to `/v1/messages` sees the whole conversation, top to bottom. To "continue", you accumulate messages and re-send the full array on the next call.

For tool use, the rhythm is fixed:

```
1. You send:        user message
2. API returns:     assistant message containing tool_use blocks  +  stop_reason="tool_use"
3. You run:         the tools yourself, locally
4. You send back:   the FULL prior history, plus a new user turn containing tool_result blocks
5. API returns:     either another assistant turn with more tool_use blocks (→ goto 3),
                    or a final text answer with stop_reason="end_turn" (→ done)
```

Tool execution itself is **client-side** — Anthropic never sees your tool code, only its outputs. The model's job is to decide *when* to call a tool and *with what arguments*; your job is to dispatch and report results.

---

## The three rules

1. **Echo the assistant turn verbatim** before appending tool results. Don't rewrite the text, don't drop the `tool_use` blocks, don't strip `thinking` signatures. The model needs to see what it asked for.
2. **`tool_result.tool_use_id` MUST match a `tool_use.id`** from the assistant turn. Mismatch → `400`. Every `tool_use` must get exactly one corresponding `tool_result` before the next call.
3. **Tool results live in a `user` role turn.** Yes, *user*, even though they came from your code — the API treats tool outputs as new input feeding into the model's next decision.

---

## The full conversation, turn by turn

This is the actual run from `claude/07_tool_use_manual.py`. Two tools were defined:

```python
{
  "name": "get_capital",
  "description": "Look up the capital city of a country.",
  "input_schema": {
    "type": "object",
    "properties": {"country": {"type": "string", "description": "Country name in English."}},
    "required": ["country"]
  }
},
{
  "name": "calculator",
  "description": "Evaluate a basic arithmetic expression. Use this for any math, even simple addition.",
  "input_schema": {
    "type": "object",
    "properties": {"expression": {"type": "string", "description": "..."}},
    "required": ["expression"]
  }
}
```

The user asked:

> "What is the capital of Japan, and what is sqrt(2) to 5 decimal places? Use your tools."

The calculator tool intentionally runs in a tiny sandbox where only `math.*` is exposed — neither `round` nor the bare `math` namespace works. This forces the model to retry, which is a great illustration of error recovery.

### Turn 1 — kickoff

**`messages` array sent to the API:**

```json
[
  {"role": "user", "content": "What is the capital of Japan, and what is sqrt(2) to 5 decimal places? Use your tools."}
]
```

**Response:**

```json
{
  "role": "assistant",
  "stop_reason": "tool_use",
  "content": [
    {"type": "text", "text": "I'll look up both in parallel."},
    {"type": "tool_use", "id": "toolu_01UZ...", "name": "get_capital", "input": {"country": "Japan"}},
    {"type": "tool_use", "id": "toolu_01Sz...", "name": "calculator", "input": {"expression": "round(math.sqrt(2), 5)"}}
  ]
}
```

Observations:
- **Two `tool_use` blocks in one assistant turn** — Claude is calling both tools in parallel.
- Each block has a unique `id` (`toolu_...`) you'll need to reference when reporting results.
- The model added a preamble `text` block before the tool calls. Either text or tool_use can come first — always iterate the whole `content` array, don't assume an order.

### Step 3 — run the tools (local, your code)

```python
get_capital(country="Japan")                      # → "Tokyo"
calculator(expression="round(math.sqrt(2), 5)")   # → "ERROR: name 'round' is not defined"
```

The sandbox doesn't expose `round`, so the second call returns an error string. We mark it `is_error=True` when sending it back — this signals to the model that something went wrong and lets it recover.

### Turn 2 — send results back

Build the new `messages` array. Append the assistant turn verbatim, then add a user turn containing one `tool_result` per `tool_use`:

```json
[
  // ─── original user turn ─────────────────────────────────────────────────
  {"role": "user", "content": "What is the capital of Japan, and what is sqrt(2) to 5 decimal places? Use your tools."},

  // ─── assistant turn from turn 1 — echoed back EXACTLY ───────────────────
  {"role": "assistant", "content": [
    {"type": "text", "text": "I'll look up both in parallel."},
    {"type": "tool_use", "id": "toolu_01UZ...", "name": "get_capital", "input": {"country": "Japan"}},
    {"type": "tool_use", "id": "toolu_01Sz...", "name": "calculator", "input": {"expression": "round(math.sqrt(2), 5)"}}
  ]},

  // ─── NEW user turn — one tool_result per tool_use, matching by id ──────
  {"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "toolu_01UZ...", "content": "Tokyo", "is_error": false},
    {"type": "tool_result", "tool_use_id": "toolu_01Sz...", "content": "ERROR: name 'round' is not defined", "is_error": true}
  ]}
]
```

**Response** (still `stop_reason: "tool_use"` — the model wants to retry):

```json
{
  "role": "assistant",
  "stop_reason": "tool_use",
  "content": [
    {"type": "text", "text": "Let me retry the calculation:"},
    {"type": "tool_use", "id": "toolu_01Mb...", "name": "calculator", "input": {"expression": "math.floor(math.sqrt(2) * 100000) / 100000"}}
  ]
}
```

The model saw `is_error: true`, read the error message, and adjusted — it noticed `round` was unavailable and tried a different expression.

### Turn 3 — another retry

Run the new expression locally:

```python
calculator(expression="math.floor(math.sqrt(2) * 100000) / 100000")
# → "ERROR: name 'math' is not defined"
```

Still failing — `math` itself isn't exposed in the sandbox. Append the tool_result. `messages` now has 5 entries: 1 user + 1 assistant + 1 user(results) + 1 assistant + 1 user(results).

**Response:**

```json
{
  "role": "assistant",
  "stop_reason": "tool_use",
  "content": [
    {"type": "tool_use", "id": "toolu_01Hs...", "name": "calculator", "input": {"expression": "2 ** 0.5"}}
  ]
}
```

The model adjusted again — dropped the `math.` namespace entirely and used the operator form.

### Turn 4 — final answer

Run the tool: `calculator("2 ** 0.5")` → `"1.4142135623730951"`. Append the tool_result and call the API a fourth time. The `messages` array is now 7 entries long.

**Response** (`stop_reason: "end_turn"` — we're done):

```json
{
  "role": "assistant",
  "stop_reason": "end_turn",
  "content": [
    {"type": "text", "text": "Here are your answers:\n\n- **Capital of Japan:** Tokyo\n- **√2 to 5 decimal places:** 1.41421"}
  ]
}
```

No more `tool_use` blocks. Loop exits.

---

## Visualizing the messages array growing

```
After turn 1 (kickoff):           [user]
After API returns:                [user, assistant(text + tool_use × 2)]         ← stop_reason=tool_use
After you append tool_results:    [user, assistant, user(tool_results × 2)]
After API returns turn 2:         [user, assistant, user, assistant(tool_use)]   ← stop_reason=tool_use
After you append tool_results:    [user, assistant, user, assistant, user]
After API returns turn 3:         [user, assistant, user, ..., assistant(tool_use)]
After you append tool_results:    [user, assistant, user, ..., user]
After API returns turn 4:         [...] + assistant(text only)                   ← stop_reason=end_turn ✓
```

The array always grows in a strict pattern: **user → assistant → user → assistant → ...** The assistant's "narration + tool calls" go in one turn. Your "here are the results" go in the next user turn. Then the model either calls more tools (another assistant turn) or wraps up with text.

---

## The loop in code

The whole thing is a `while True` that exits on `end_turn`:

```python
messages = [{"role": "user", "content": "What is the capital of Japan..."}]

while True:
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        tools=TOOLS,
        messages=messages,
    )

    # Rule 1: echo the assistant turn back verbatim — preserves tool_use
    # blocks AND any thinking-block signatures for the next call.
    messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason == "end_turn":
        break

    # Run every tool_use block and collect the results in order.
    tool_results = []
    for block in response.content:
        if block.type == "tool_use":
            result, is_error = dispatch(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,                # Rule 2: MUST match
                "content": result,
                "is_error": is_error,
            })

    # Rule 3: tool results go in a USER turn.
    messages.append({"role": "user", "content": tool_results})
```

Six lines of real logic. Everything else is boilerplate.

---

## Doing it with raw cURL

The wire format is identical. Here's turn 1 of the same conversation as a cURL call:

```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 1024,
    "tools": [{
      "name": "get_weather",
      "description": "Get the current weather for a city.",
      "input_schema": {
        "type": "object",
        "properties": {
          "city": {"type": "string", "description": "City name, e.g. Tokyo"},
          "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
        },
        "required": ["city"]
      }
    }],
    "messages": [
      {"role": "user", "content": "What is the weather in Tokyo right now? Use the tool."}
    ]
  }'
```

Response (truncated):
```json
{
  "content": [
    {"type": "text", "text": "I'll check the current weather in Tokyo for you."},
    {"type": "tool_use", "id": "toolu_014HP...", "name": "get_weather", "input": {"city": "Tokyo"}}
  ],
  "stop_reason": "tool_use"
}
```

Turn 2 — same `tools` array, full `messages` history echoed back, plus the new `tool_result`:

```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 1024,
    "tools": [{
      "name": "get_weather",
      "description": "Get the current weather for a city.",
      "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}, "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}},
        "required": ["city"]
      }
    }],
    "messages": [
      {"role": "user", "content": "What is the weather in Tokyo right now? Use the tool."},
      {"role": "assistant", "content": [
        {"type": "text", "text": "I will check the current weather in Tokyo for you."},
        {"type": "tool_use", "id": "toolu_014HP...", "name": "get_weather", "input": {"city": "Tokyo"}}
      ]},
      {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_014HP...", "content": "18°C, light rain, humidity 78%"}
      ]}
    ]
  }'
```

The model now produces the final text answer with `stop_reason: "end_turn"`.

> If you copy-paste these and get `"unexpected control character in string"`, the JSON has a raw newline inside one of the string values. Use `\n` inside JSON strings, or build the body with `jq -n --arg q "$YOUR_TEXT" '{...}'` to escape automatically.

---

## Controlling tool selection — `tool_choice`

By default, the model decides whether to call a tool. Override with `tool_choice`:

```json
{"type": "auto"}                                  // model decides (default)
{"type": "any"}                                   // must call SOME tool
{"type": "tool", "name": "get_capital"}           // must call THIS specific tool
{"type": "none"}                                  // tools disabled for this turn
```

Cap to one tool per turn (no parallel calls):
```json
{"type": "auto", "disable_parallel_tool_use": true}
```

When you set `"type": "any"` or `"type": "tool"`, the first response is guaranteed to contain a `tool_use` block — useful when you've already determined that a tool MUST run (e.g., user clicked a button).

---

## Handling tool errors — `is_error: true`

If your tool fails, send the failure back rather than throwing. Set `is_error: true` on the `tool_result` and put a useful error message in `content`:

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_01Sz...",
  "content": "ERROR: name 'round' is not defined. Try using math.floor(x * 100000) / 100000 instead.",
  "is_error": true
}
```

The model can read the error, adjust its approach, and call the tool again with different arguments — as it did three times in the walkthrough above. Without `is_error: true`, the model might treat the error string as a successful result.

Good error messages tell the model **what went wrong** and **how to fix it**. Bad: `"Internal error"`. Better: `"City 'Mars' not found. Provide a valid Earth city name."`

---

## Parallel tool calls

When two tool calls are independent, the model will often emit both in a single assistant turn (as it did in turn 1 above). You **must** return one `tool_result` per `tool_use` before the next call — the API rejects the next request if any `tool_use.id` is missing a matching `tool_result`.

In Python the dispatch is naturally serial:
```python
for block in response.content:
    if block.type == "tool_use":
        result = dispatch(block.name, block.input)
        tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
```

If your tools are async-safe and independent, parallelize the dispatch step:
```python
import asyncio

async def run_one(block):
    result = await async_dispatch(block.name, block.input)
    return {"type": "tool_result", "tool_use_id": block.id, "content": result}

tool_uses = [b for b in response.content if b.type == "tool_use"]
tool_results = await asyncio.gather(*[run_one(b) for b in tool_uses])
```

Saves wall time on slow tools (DB queries, HTTP calls). Make sure your tools are actually safe to run concurrently (no shared mutable state).

---

## Strict mode — guaranteed schema-valid inputs

Add `"strict": true` to a tool definition to enforce the input schema strictly:

```json
{
  "name": "book_flight",
  "description": "Book a flight.",
  "strict": true,
  "input_schema": {
    "type": "object",
    "properties": {
      "destination": {"type": "string"},
      "passengers":  {"type": "integer", "enum": [1, 2, 3, 4]}
    },
    "required": ["destination", "passengers"],
    "additionalProperties": false
  }
}
```

With `strict: true`, the model's `tool_use.input` is guaranteed to validate against the schema — no `passengers: "two"` slipping through, no extra fields, no missing required fields. The same JSON Schema restrictions as structured outputs apply (`additionalProperties: false` required on all objects, no numerical bounds, no recursion).

Use it for any tool whose inputs you don't want to validate by hand on every call.

---

## Manual loop vs Tool Runner

The SDK provides a beta `tool_runner` that writes the loop for you. The trade-off:

| | Manual loop | Tool runner |
|---|---|---|
| Loop logic | You write it | SDK handles it |
| Schemas | Hand-written JSON Schema | Auto-derived from type hints + docstrings |
| Tool result appending | You do it | SDK does it |
| Logging/auditing each turn | Easy | Harder — wraps the loop |
| Human-in-the-loop approval | Easy — pause before dispatching | Hard — would need to subclass |
| Concurrent dispatch | Easy via `asyncio.gather` | Less flexible |
| Best for | Production code with custom hooks | Quick prototypes, internal tools |

Tool runner example (see [`claude/08_tool_runner.py`](claude/08_tool_runner.py) for the full version):

```python
from anthropic import beta_tool

@beta_tool
def get_capital(country: str) -> str:
    """Look up the capital city of a country.

    Args:
        country: Country name in English.
    """
    return {"Japan": "Tokyo", "France": "Paris"}.get(country, f"Unknown: {country}")

runner = client.beta.messages.tool_runner(
    model="claude-opus-4-8",
    max_tokens=1024,
    tools=[get_capital],
    messages=[{"role": "user", "content": "Capital of Japan?"}],
)

for message in runner:        # yields each intermediate Message
    print(message)            # auto-loops until end_turn
```

The schema is built from the type hints (`country: str`) and the docstring's `Args:` block.

---

## Common pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| `400: tool_use_id <id> has no matching tool_result` | You forgot a `tool_result` for one of the `tool_use` blocks (or your IDs don't match) | Build `tool_results` by iterating `response.content` — one result per `tool_use` block, copying `block.id` exactly |
| Model keeps calling the same broken tool | You returned the error as plain `content` without `is_error: true` | Set `is_error: true` and put a useful error message in `content` |
| Tool fires when it shouldn't | Tool description is too eager (e.g., `"Always use this for math"`) | Tighten the description: `"Use this when the user asks for a numeric calculation."` |
| Tool doesn't fire when it should | Description is too vague | Be specific about *when* and *what for*. Add an example: `"For instance, use this tool when the user asks 'what is sqrt(2)?'"` |
| Loop runs forever | No `max_turns` safety guard | Wrap with `for turn in range(8):` or break on `turn > N` |
| `BadRequestError: messages: roles must alternate...` | You appended two consecutive `user` or `assistant` turns | Always alternate. If you have parallel tool results, group them in ONE user turn (a single content list with multiple `tool_result` blocks) |
| Lost cache hits when tools change | Tools render at offset 0 in the prefix — any change invalidates the whole cache | Keep `tools` array stable across requests; sort it deterministically (e.g. by name) |

---

## A complete minimal end-to-end Python example

```python
import anthropic

client = anthropic.Anthropic()

TOOLS = [{
    "name": "get_weather",
    "description": "Get current weather for a city.",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}]

def get_weather(city: str) -> str:
    return f"{city}: 18°C, light rain"      # your real impl here

messages = [{"role": "user", "content": "What's the weather in Tokyo? Use the tool."}]

for _ in range(8):                          # cap iterations to be safe
    resp = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        tools=TOOLS,
        messages=messages,
    )
    messages.append({"role": "assistant", "content": resp.content})

    if resp.stop_reason == "end_turn":
        break

    tool_results = []
    for block in resp.content:
        if block.type == "tool_use":
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": get_weather(**block.input),
            })
    messages.append({"role": "user", "content": tool_results})

print(next(b.text for b in resp.content if b.type == "text"))
```

Run it: every loop iteration is one round-trip to `/v1/messages`. Most simple queries finish in 2 round-trips (kickoff → tool_use, results → end_turn). Multi-step plans can take 5–10. Always cap iterations as a safety net.

---

## Related reading

- [`WALKTHROUGH.md`](WALKTHROUGH.md) — full tour of the Messages API surface (system prompts, vision, streaming, structured output, caching, etc.)
- [`claude/07_tool_use_manual.py`](claude/07_tool_use_manual.py) — runnable manual loop, 100 lines
- [`claude/08_tool_runner.py`](claude/08_tool_runner.py) — runnable tool runner version, 60 lines
- Official tool use guide: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview`
