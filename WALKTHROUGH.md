# Claude LLM I/O — Hands-on Walkthrough

A guided tour of every type of input and output for the Claude Messages API, with real captured runs.

**Model used throughout:** `claude-opus-4-8` (1M context, 128K max output).

## How to use this project

```bash
# One-time setup (already done if you followed the conversation)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run any script from the project root
.venv/bin/python claude/01_basic.py
.venv/bin/python claude/05_thinking_and_effort.py

# Try a different model
ANTHROPIC_MODEL=claude-haiku-4-5 .venv/bin/python claude/01_basic.py
```

The API key lives at `claude/apikey/mingwei.apikey` (gitignored). `claude/_common.py` reads it, builds the SDK client, and exports two helpers (`dump`, `section`) used across the scripts.

Suggested reading order: top to bottom. Each script builds on the previous concepts.

---

## Running with cURL instead

Every section below also includes a copy-pasteable cURL command — useful if you want to poke at the API without Python, or paste the request into a tool like Postman. **Run all cURL commands from the project root** so the relative path to the API key works.

The three required headers, present on every request:

```bash
-H "x-api-key: $(cat claude/apikey/mingwei.apikey)"
-H "anthropic-version: 2023-06-01"
-H "content-type: application/json"
```

To pretty-print responses, pipe through `jq`:
```bash
curl ... | jq
```

**Shell quoting gotcha** — JSON in `-d '...'` is single-quoted, so single quotes inside your prompt (`don't`, `it's`) and **literal newlines** inside string values both break the JSON parser. Two robust fixes:

```bash
# 1) Use a heredoc — anything goes inside, including quotes
curl ... -d @- <<'EOF'
{ "model": "claude-opus-4-8", "max_tokens": 256,
  "messages": [{"role": "user", "content": "Don't worry about quotes here!"}] }
EOF

# 2) Build the body with jq -n — handles any text, including multi-line
QUESTION="Write a poem
about cats"
jq -n --arg q "$QUESTION" '{model:"claude-opus-4-8", max_tokens:256, messages:[{role:"user", content:$q}]}' \
  | curl ... -d @-
```

---

## Mental model

Every Claude API call goes through one endpoint: `POST /v1/messages`. The request is always `{model, max_tokens, messages, ...}`. The response is always `{id, role: "assistant", content: [...], stop_reason, usage, ...}`. Tools, thinking, streaming, caching, structured output — they're all just extra fields on this same shape.

```
REQUEST                              RESPONSE
─────────────────────────            ─────────────────────────
model            (required)          id           — unique message ID
max_tokens       (required)          type         — always "message"
messages         (required)          role         — always "assistant"
system           (optional)          model        — which model served it
tools            (optional)          content[]    — list of blocks
tool_choice      (optional)          stop_reason  — why generation stopped
thinking         (optional)          stop_sequence— which custom stop fired
output_config    (optional)          stop_details — refusal info (if applicable)
cache_control    (optional)          usage        — token counts
stream           (optional)
stop_sequences   (optional)
metadata         (optional)
```

**Content blocks** are the universal vocabulary. A message's `content` is always a *list of typed blocks* — both directions. Common types you'll see:

| Block type | Direction | Carries |
|------------|-----------|---------|
| `text` | both | `.text` — plain text |
| `image` | input | `.source` — base64 / url / file_id |
| `document` | input | `.source` — PDF or text doc |
| `thinking` | output | `.thinking` (reasoning), `.signature` (opaque) |
| `tool_use` | output | `.name`, `.input` — model wants to call a tool |
| `tool_result` | input | `.tool_use_id`, `.content` — your reply to a tool_use |
| `server_tool_use` | output | Anthropic-side tool invocation (web_search, etc.) |

---

## 01 — Basic request

**Concept:** the minimum viable request, and every field on the response.

### Input — Python
```python
client.messages.create(
    model="claude-opus-4-8",
    max_tokens=256,
    messages=[
        {"role": "user", "content": "In one sentence: what does the LLM Messages API return?"},
    ],
)
```

### Input — cURL
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 256,
    "messages": [{"role": "user", "content": "In one sentence: what does the LLM Messages API return?"}]
  }' | jq
```

### Output (excerpt)
```json
{
  "id": "msg_01JdsYpq2EzhXrrAwd2EBmZB",
  "content": [
    {
      "type": "text",
      "text": "The LLM Messages API returns a model-generated response (typically including the assistant's reply text, role, stop reason, and token usage metadata) based on a provided conversation history of messages."
    }
  ],
  "model": "claude-opus-4-8",
  "role": "assistant",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "type": "message",
  "usage": {
    "input_tokens": 29,
    "output_tokens": 61,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "service_tier": "standard"
  }
}
```

### Takeaways
- `response.content` is **always a list**, even for a one-sentence reply. Index into it and check `.type` before reading `.text`.
- `stop_reason="end_turn"` is the success path. See script 06 for the others.
- The API is stateless — nothing persists between calls.

---

## 02 — System prompt + multi-turn conversation

**Concept:** `system` shapes behavior; conversation history is re-sent on every call (stateless API).

### Input — system as a string (Python)
```python
client.messages.create(
    model="claude-opus-4-8",
    max_tokens=128,
    system="Respond only in pirate slang. Never use modern English.",
    messages=[{"role": "user", "content": "How's the weather today?"}],
)
```

### Input — system as a string (cURL)
Note: the prompt uses `'` for the apostrophe in `How's` to dodge the single-quote-inside-single-quote shell trap.
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 128,
    "system": "Respond only in pirate slang. Never use modern English.",
    "messages": [{"role": "user", "content": "How is the weather today?"}]
  }' | jq
```
**Output:** *"Arrr, the skies be a fickle wench today, matey! The winds be howlin' from the east..."*

### Input — system as a list (enables `cache_control` per block)
```python
system=[
    {"type": "text", "text": "You are an expert on Mars geology."},
    {"type": "text", "text": "Always cite the source (Mariner / Viking / Curiosity / Perseverance)."},
]
```
**Output:** *"Olympus Mons is the tallest volcano in the solar system, rising about 22 km above the surrounding plains, as first revealed by Mariner 9 imaging in 1971–1972."*

### Input — multi-turn (resend history)
```python
history = [
    {"role": "user", "content": "My favourite colour is sea-foam green."},
]
# Turn 1 → get reply → append to history → ask follow-up
history.append({"role": "assistant", "content": "Sea-foam green is a lovely, calming shade!"})
history.append({"role": "user", "content": "What colour did I just say I liked?"})
```
**Output:** *"Sea-foam green."*

### Input — multi-turn (cURL, turn 2)
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 64,
    "messages": [
      {"role": "user", "content": "My favourite colour is sea-foam green."},
      {"role": "assistant", "content": "Sea-foam green is a lovely, calming shade!"},
      {"role": "user", "content": "What colour did I just say I liked?"}
    ]
  }' | jq -r '.content[0].text'
```

### Takeaways
- `system` is an instruction the model treats as authoritative (persona, format, hard rules).
- The list form of `system` enables per-block `cache_control` (see script 10).
- Multi-turn = you resend the WHOLE history each time. First message must be `user`.
- **Note:** On Opus 4.6/4.8 and Sonnet 4.6, ending `messages` with `role: "assistant"` (a "prefill") returns 400 — use structured outputs (script 09) instead.

---

## 03 — Multimodal content blocks (text + image)

**Concept:** a single user turn's `content` can be a *list of typed blocks*. Mix text, images, documents.

### Input — Python (base64)
```python
messages=[{
    "role": "user",
    "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
        {"type": "text",  "text": "Describe what you see in this image in one short sentence."},
    ],
}]
```
The script generates a tiny PNG on the fly: a red-bordered rectangle on a beige background with the text "HELLO CLAUDE".

### Input — cURL (image by URL — simplest copyable form)
Base64 in cURL is ugly because the payload bloats the request body. The URL source variant is easier:
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 256,
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image", "source": {"type": "url", "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/320px-PNG_transparency_demonstration_1.png"}},
        {"type": "text", "text": "Describe what you see in one sentence."}
      ]
    }]
  }' | jq -r '.content[0].text'
```

For base64 from cURL, pipe `base64` through `jq -n --arg`:
```bash
B64=$(base64 -i path/to/image.png | tr -d '\n')
jq -n --arg b "$B64" '{model:"claude-opus-4-8", max_tokens:256, messages:[{role:"user", content:[
  {type:"image", source:{type:"base64", media_type:"image/png", data:$b}},
  {type:"text",  text:"Describe what you see."}
]}]}' \
  | curl https://api.anthropic.com/v1/messages \
      -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
      -H "anthropic-version: 2023-06-01" \
      -H "content-type: application/json" \
      -d @-
```

### Output
```text
A red-bordered rectangular frame on a beige background contains the text "HELLOCLAUDE" in dark lettering.
```

### Other image/document sources
```python
{"type": "image", "source": {"type": "url",    "url": "https://example.com/img.png"}}
{"type": "image", "source": {"type": "file",   "file_id": "file_..."}}   # Files API
{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "..."}}
```

### Takeaways
- Order of blocks matters (model reads top to bottom).
- A common pattern is `[image, text]`: attach it, then ask about it.
- PDFs use `type="document"` with the same three source variants.

---

## 04 — Streaming

**Concept:** with `stream=True`, the response is a sequence of SSE events. Reassemble the final message from deltas.

### Input — Python
```python
client.messages.create(
    model="claude-opus-4-8",
    max_tokens=128,
    stream=True,                                    # <-- the only change
    messages=[{"role": "user", "content": "Write a haiku about TCP/IP."}],
)
```

### Input — cURL
The `-N` flag disables curl's output buffering so you see SSE events as they arrive.
```bash
curl -N https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 128,
    "stream": true,
    "messages": [{"role": "user", "content": "Write a haiku about TCP/IP."}]
  }'
```

### Output (event trace)
```text
message_start        → id='msg_0186J173DXFDKszTkiuke5WB', model='claude-opus-4-8'
content_block_start  → index=0, block.type='text'
content_block_delta  → text_delta 'Packets se'
content_block_delta  → text_delta 'ek their path—\nhandshake, then the data flows,'
content_block_delta  → text_delta '\nACK confirms arrival.'
content_block_stop   → index=0
message_delta        → stop_reason='end_turn', output_tokens=34
message_stop         → (end of stream)
```

### Event types
| Event | When |
|-------|------|
| `message_start` | once at the start — message metadata |
| `content_block_start` | when a new block begins (text / thinking / tool_use) |
| `content_block_delta` | incremental update; `.delta.type` tells you what kind |
| `content_block_stop` | block is finished |
| `message_delta` | `stop_reason` and final `usage` land here |
| `message_stop` | once at the end |

Delta variants: `text_delta`, `thinking_delta`, `input_json_delta` (tool args), `signature_delta`, `citations_delta`.

### Recommended helper
For most code, skip the raw iterator and use the context manager:
```python
with client.messages.stream(...) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
    final = stream.get_final_message()   # full Message object
```

---

## 05 — Adaptive thinking + effort

**Concept:** let Claude decide *when* and *how much* to think. The reasoning is exposed as `thinking` content blocks before the final `text` blocks.

### Input — Python
```python
client.messages.create(
    model="claude-opus-4-8",
    max_tokens=2048,
    thinking={"type": "adaptive", "display": "summarized"},   # show the reasoning summary
    output_config={"effort": "medium"},
    messages=[{"role": "user", "content": "A snail climbs a 30 ft well..."}],
)
```

### Input — cURL
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 2048,
    "thinking": {"type": "adaptive", "display": "summarized"},
    "output_config": {"effort": "medium"},
    "messages": [{"role": "user", "content": "A snail climbs a 30 ft well. Each day it climbs 3 ft, each night it slips back 2 ft. How many days until it reaches the top? Think it through."}]
  }' | jq
```

### Output
```text
content[0].type = 'text'
content[0].text:
28 days.

After day n, the snail is at n feet (climbs 3, slips 2 = net 1 ft/day). But on the day it reaches the top, it doesn't slip back.

So we need it to reach 30 ft during the day. At the start of day 28, it's at 27 ft (after 27 full day/night cycles). It climbs 3 ft that day → 30 ft. Done.

**Answer: 28 days.**
```

### Knob reference

| Parameter | Values | Effect |
|-----------|--------|--------|
| `thinking={"type": "adaptive"}` | required for Opus 4.8 thinking | model decides depth per request |
| `thinking={"type": "adaptive", "display": "summarized"}` | recommended if you want to *see* it | restores visible reasoning summaries (default on 4.8 is `omitted`) |
| `thinking={"type": "disabled"}` | | turn it off entirely |
| `output_config={"effort": ...}` | `low` / `medium` / `high` / `xhigh` / `max` | controls overall token spend AND thinking depth. `xhigh`/`max` Opus-only |

> **Note:** Adaptive is non-deterministic about *whether* it invokes thinking. On easy problems the model may answer directly without emitting a `thinking` block; on hard ones you'll see one or more thinking blocks before the text. Both your code and your UI should handle both cases.

### Takeaways
- Output tokens cover *both* thinking and text — budget `max_tokens` generously when adaptive is on.
- Removed on Opus 4.8: `budget_tokens` (fixed budget) and `temperature` / `top_p` / `top_k`. Use `effort` to steer instead.

---

## 06 — Every `stop_reason`

**Concept:** how the model signals *why* it stopped generating.

### Live demonstrations

**`end_turn`** — normal completion.
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 128,
    "messages": [{"role": "user", "content": "Say hello in 5 words."}]
  }' | jq '{text:.content[0].text, stop_reason}'
```
```text
{"text": "Hello, hope you're doing well!", "stop_reason": "end_turn"}
```

**`max_tokens`** — output truncated mid-thought because we capped at 20 tokens.
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 20,
    "messages": [{"role": "user", "content": "Explain the Internet Protocol in full detail."}]
  }' | jq '{text:.content[0].text, stop_reason, output_tokens:.usage.output_tokens}'
```
```text
{"text": "# The Internet Protocol (IP): A Complete Explan", "stop_reason": "max_tokens", "output_tokens": 20}
```

**`stop_sequence`** — generation halts when a custom stop string appears (the string itself is NOT included in output).
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 256,
    "stop_sequences": ["END", "###"],
    "messages": [{"role": "user", "content": "Count from 1 to 10, one per line. After 5, write END."}]
  }' | jq '{text:.content[0].text, stop_reason, stop_sequence}'
```
```text
{"text": "1\n2\n3\n4\n5\n", "stop_reason": "stop_sequence", "stop_sequence": "END"}
```

### Other values (conceptual)
| Value | Meaning |
|-------|---------|
| `tool_use` | Model wants a tool to run. See scripts 07 & 08. |
| `pause_turn` | Server-side tool loop hit iteration limit. Re-send to continue. |
| `refusal` | Safety refusal. `stop_details.category` ∈ {`cyber`, `bio`}, `stop_details.explanation` is human-readable. |
| `model_context_window_exceeded` | Context window exhausted. Compact or split. |

---

## 07 — Tool use, manual loop

**Concept:** how function calling actually works on the wire. You write the loop.

> For a full deep-dive on the tool-use rhythm (the three rules, turn-by-turn message accumulation, `tool_choice`, `is_error`, parallel calls, strict mode), see **[`TOOL_USE.md`](TOOL_USE.md)**.

### Input — define tools (Python)
```python
TOOLS = [
    {
        "name": "calculator",
        "description": "Evaluate a basic arithmetic expression. Use this for any math.",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "..."}},
            "required": ["expression"],
        },
    },
    {"name": "get_capital", "description": "Look up the capital city...", "input_schema": {...}},
]
```

### Input — turn 1 (cURL)
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
    "messages": [{"role": "user", "content": "What is the weather in Tokyo right now? Use the tool."}]
  }' | jq
```
The response will have `stop_reason: "tool_use"` and a `tool_use` block with an `id` like `toolu_014HP...`. To complete the turn, send turn 2 with the assistant message echoed back and a `tool_result` block.

### Input — turn 2 (cURL, after running the tool yourself)
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
  }' | jq
```
Replace `toolu_014HP...` with the actual id from turn 1's response. This second call should return `stop_reason: "end_turn"` with the final answer.

### Query
> "What is the capital of Japan, and what is sqrt(2) to 5 decimal places? Use your tools."

### Output — the agentic loop in action
```text
--- Turn 1: calling /v1/messages ---
stop_reason: tool_use
  tool_use → name='get_capital', input={'country': 'Japan'}, id='toolu_01UZ...'
           → result='Tokyo' (is_error=False)
  tool_use → name='calculator', input={'expression': 'round(math.sqrt(2), 5)'}, id='toolu_01Sz...'
           → result="ERROR: name 'round' is not defined" (is_error=True)

--- Turn 2: calling /v1/messages ---
stop_reason: tool_use
  tool_use → name='calculator', input={'expression': 'math.floor(math.sqrt(2) * 100000) / 100000'}
           → result="ERROR: name 'math' is not defined" (is_error=True)

--- Turn 3: calling /v1/messages ---
stop_reason: tool_use
  tool_use → name='calculator', input={'expression': '2 ** 0.5'}
           → result='1.4142135623730951' (is_error=False)

--- Turn 4: calling /v1/messages ---
stop_reason: end_turn

FINAL ANSWER:
- **Capital of Japan:** Tokyo
- **√2 to 5 decimal places:** 1.41421
```

### Wire-level shape (what gets sent back)

After receiving `tool_use` blocks, you append the assistant turn verbatim and reply with `tool_result` blocks in a user turn:
```python
messages.append({"role": "assistant", "content": response.content})   # echo assistant
messages.append({"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "toolu_01UZ...", "content": "Tokyo", "is_error": False},
    {"type": "tool_result", "tool_use_id": "toolu_01Sz...", "content": "ERROR: ...", "is_error": True},
]})
```

### Takeaways
- `stop_reason="tool_use"` means **wait for tools**. The model is paused.
- The `tool_use_id` MUST match the `tool_use` block. The API rejects unmatched IDs.
- `is_error=True` on a `tool_result` lets the model recover (it did — retried twice before succeeding).
- `tool_choice` controls when the model is *allowed* to call tools: `{"type": "auto"}` (default), `"any"` (must call something), `{"type": "tool", "name": "..."}` (force), `"none"` (forbid).

---

## 08 — Tool runner (SDK helper)

**Concept:** the same agentic loop, but the SDK writes the boilerplate.

> **No cURL equivalent.** The tool runner IS an SDK helper — it wraps the same `POST /v1/messages` calls that the manual loop in section 07 makes. From cURL, you do the manual loop.

### Input
```python
from anthropic import beta_tool

@beta_tool
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression. Use this for ANY math.

    Args:
        expression: Python-style arithmetic, e.g. '2 ** 0.5'.
    """
    ...

@beta_tool
def get_capital(country: str) -> str:
    """Look up the capital city of a country.

    Args:
        country: Country name in English.
    """
    ...

runner = client.beta.messages.tool_runner(
    model=MODEL,
    max_tokens=1024,
    tools=[calculator, get_capital],
    messages=[{"role": "user", "content": "What is the capital of Kenya, and what is sqrt(2) to 5 decimal places?"}],
)

for message in runner:                    # auto-loops; yields each intermediate Message
    ...
```

### Output
```text
--- runner step 1 ---
stop_reason: tool_use
  text       : "I'll look up both pieces of information in parallel."
  tool_use   : get_capital({'country': 'Kenya'})
  tool_use   : calculator({'expression': 'round(math.sqrt(2), 5)'})

--- runner step 2 ---
stop_reason: tool_use
  text       : 'Let me retry the calculation:'
  tool_use   : calculator({'expression': 'math.sqrt(2)'})

--- runner step 3 ---
stop_reason: tool_use
  tool_use   : calculator({'expression': '2 ** 0.5'})

--- runner step 4 ---
stop_reason: end_turn
  text       : '- **Capital of Kenya:** Nairobi\n- **√2 to 5 decimal places:** 1.41421'
```

### Manual loop vs tool runner — when to pick which

| | Manual loop (07) | Tool runner (08) |
|---|---|---|
| Loop | You write it | SDK handles it |
| Schemas | Hand-written JSON Schema | Auto-derived from type hints + docstring |
| Tool result blocks | You append them | SDK appends them |
| Hook between steps (logging, approval, gating) | Easy | Harder |
| Best for | Production code that needs control | Quick prototypes, glue scripts |

---

## 09 — Structured output

**Concept:** force the response to match a schema. Pydantic-typed or raw JSON Schema.

### Input — Pydantic (recommended)
```python
class Invoice(BaseModel):
    invoice_number: str
    customer: str
    items: list[LineItem]
    total_usd: float
    payment_terms: Literal["net_15", "net_30", "due_on_receipt"]

resp = client.messages.parse(                       # .parse() not .create()
    model="claude-opus-4-8",
    max_tokens=1024,
    output_format=Invoice,                          # <-- pass the model class
    messages=[{"role": "user", "content": "Extract a structured invoice from this email: Hey, here's invoice #A-2391 for Acme Coyote Supplies. We sent over 12 rocket sleds at $499 each and 200 lbs of birdseed at $2.50/lb. Total comes to $6,488. Net 30 terms."}],
)

invoice: Invoice = resp.parsed_output               # <-- typed instance
```

### Output
```text
type(resp.parsed_output) = Invoice
invoice.invoice_number   = 'A-2391'
invoice.customer         = 'Acme Coyote Supplies'
invoice.total_usd        = 6488.0
invoice.payment_terms    = 'net_30'
invoice.items:
  -  12 x 'Rocket sleds' @ $499.0
  - 200 x 'Birdseed (lbs)' @ $2.5

Raw JSON text:
{"invoice_number":"A-2391","customer":"Acme Coyote Supplies","items":[...],"total_usd":6488,"payment_terms":"net_30"}
```

### Input — raw JSON Schema, Python
```python
client.messages.create(
    model="claude-opus-4-8",
    max_tokens=512,
    output_config={"format": {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "sentiment":  {"type": "string", "enum": ["positive", "neutral", "negative"]},
                "confidence": {"type": "number"},
                "keywords":   {"type": "array", "items": {"type": "string"}},
            },
            "required": ["sentiment", "confidence", "keywords"],
            "additionalProperties": False,        # required for all objects
        },
    }},
    messages=[{"role": "user", "content": "Classify: 'I waited 45 minutes for a cold coffee. Never again.'"}],
)
```

### Input — raw JSON Schema, cURL
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "max_tokens": 512,
    "output_config": {
      "format": {
        "type": "json_schema",
        "schema": {
          "type": "object",
          "properties": {
            "sentiment":  {"type": "string", "enum": ["positive", "neutral", "negative"]},
            "confidence": {"type": "number"},
            "keywords":   {"type": "array", "items": {"type": "string"}}
          },
          "required": ["sentiment", "confidence", "keywords"],
          "additionalProperties": false
        }
      }
    },
    "messages": [{"role": "user", "content": "Classify: I waited 45 minutes for a cold coffee. Never again."}]
  }' | jq -r '.content[0].text' | jq
```
The final `| jq` pretty-prints the JSON returned in the text block.

### Output
```text
sentiment  : 'negative'
confidence : 0.97
keywords   : ['waited', '45 minutes', 'cold coffee', 'never again']
```

### Schema limitations
- All objects MUST have `additionalProperties: false`.
- No numeric/length constraints (`minimum`, `maxLength`, etc. — SDK strips them).
- No recursive schemas.
- Cannot combine with citations or assistant prefills.

### Strict tool inputs
The same idea applies to tool inputs — add `"strict": True` to a tool definition to enforce schema conformance on the model's `tool_use.input`.

---

## 10 — Prompt caching

**Concept:** cache long shared prefixes; pay ~0.1× on cache reads vs full price on uncached input.

### Input — Python
```python
system = [
    {"type": "text", "text": "You answer questions strictly from the REFERENCE DOCUMENT below."},
    {
        "type": "text",
        "text": f"REFERENCE DOCUMENT:\n{big_doc}",         # ~25K tokens of context
        "cache_control": {"type": "ephemeral"},            # <-- cache up to here
    },
]
```

### Input — cURL
The marker goes on a `system` text block. Use `jq -n` to inject a large reference document without dealing with embedded newlines:
```bash
DOC=$(printf 'The Common Lisp HyperSpec documents every function, macro, and special operator. ...\n%.0s' {1..500})

jq -n --arg doc "$DOC" '{
  model: "claude-opus-4-8",
  max_tokens: 256,
  system: [
    {type: "text", text: "You answer questions strictly from the REFERENCE DOCUMENT below."},
    {type: "text", text: ("REFERENCE DOCUMENT:\n" + $doc), cache_control: {type: "ephemeral"}}
  ],
  messages: [{role: "user", content: "What does the HyperSpec document?"}]
}' | curl -s https://api.anthropic.com/v1/messages \
        -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
        -H "anthropic-version: 2023-06-01" \
        -H "content-type: application/json" \
        -d @- | jq '.usage'
```

Run it twice. First call writes the cache (`cache_creation_input_tokens > 0`); second call reads it (`cache_read_input_tokens > 0`).

> **Caveat:** the minimum cacheable prefix on Opus 4.8 is 4096 tokens. The `DOC` variable above needs to be big enough to clear that threshold or `cache_creation_input_tokens` will silently stay 0. The script version (`claude/10_prompt_caching.py`) generates ~25K tokens to be safe.

### Output
```text
Reference doc length: 66,500 chars

== RUN 1 — cold cache (expect cache_creation > 0, cache_read = 0) ==
input_tokens                  :      6   (uncached, full price)
cache_creation_input_tokens   :     15   (written to cache, ~1.25x)
cache_read_input_tokens       :  25043   (served from cache, ~0.1x)
output_tokens                 :     37
answer: According to the reference document, the Common Lisp HyperSpec documents every function, macro, and special operator.

== RUN 2 — warm cache (expect cache_read > 0, cache_creation = 0) ==
input_tokens                  :      6   (uncached, full price)
cache_creation_input_tokens   :     22   (written to cache, ~1.25x)
cache_read_input_tokens       :  25043   (served from cache, ~0.1x)
output_tokens                 :     58
answer: According to the reference document, Lisp's S-expression syntax is mentioned as useful because it treats code and data uniformly, enabling powerful metaprogramming.
```

> **Note on this run:** both runs show `cache_read_input_tokens=25043` because the cache from earlier verification runs was still warm (default TTL is 5 minutes). On a truly cold first run, run 1 would show `cache_creation_input_tokens=25043, cache_read_input_tokens=0`. Wait 5+ minutes between attempts to see the cold-start pattern.

### Caching rules
- It's a **prefix match**. One byte changes anywhere in the prefix → whole cache invalidates.
- Render order is `tools` → `system` → `messages`. A `cache_control` marker caches everything up to and including its block.
- Minimum cacheable prefix on Opus 4.8: **4096 tokens**. Shorter prompts silently won't cache (no error).
- Max 4 `cache_control` breakpoints per request.
- Default TTL: 5 min. Add `"ttl": "1h"` for 1-hour (write cost 2× instead of 1.25×).

### Common invalidators (silent killers)
- `datetime.now()` or `uuid4()` in the system prompt
- `json.dumps(d)` without `sort_keys=True` (non-deterministic order)
- Adding/removing a tool — tools render at offset 0, invalidates everything
- Switching models — caches are model-scoped

---

## 11 — Token counting

**Concept:** estimate input tokens before sending. Free, fast, identical shape to `messages.create`.

### Input — Python
```python
client.messages.count_tokens(
    model="claude-opus-4-8",
    system="You are a careful shopping assistant.",
    tools=[{"name": "search_inventory", "description": "...", "input_schema": {...}}],
    messages=[{"role": "user", "content": "Do you have any blue ergonomic chairs under $300?"}],
)
```

### Input — cURL
A different endpoint — `/v1/messages/count_tokens` instead of `/v1/messages`. Same body shape minus `max_tokens`.
```bash
curl https://api.anthropic.com/v1/messages/count_tokens \
  -H "x-api-key: $(cat claude/apikey/mingwei.apikey)" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "system": "You are a careful shopping assistant.",
    "tools": [{
      "name": "search_inventory",
      "description": "Search the product inventory.",
      "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"]
      }
    }],
    "messages": [{"role": "user", "content": "Do you have any blue ergonomic chairs under $300?"}]
  }' | jq
```
**Output:** `{"input_tokens": 789}`

### Output
```text
count_tokens — tiny prompt       : input_tokens = 15
count_tokens — system + tools    : input_tokens = 789
```

### Use cases
1. **Cost estimation before send.**
   ```python
   estimated_usd = count.input_tokens * (5.00 / 1_000_000)   # Opus 4.8 input price
   ```
2. **Conversation compaction trigger.** Hit ~80% of the context window? Time to summarize.
3. **Cache-miss debugging.** If `cache_read_input_tokens` is 0, run `count_tokens` on two consecutive requests. If the counts differ for what should be the same prefix, something is varying byte-for-byte.

---

## Where to go next

What this study covers: text, vision (image), document (mentioned), streaming, thinking, effort, stop reasons, custom tools (manual + runner), structured output, prompt caching, token counting.

What's left to explore (say the word and I'll build scripts for these):

| Concept | What it adds |
|---------|--------------|
| **Files API** (`client.beta.files`) | Upload once, reference by `file_id` across many requests |
| **Batches API** (`client.messages.batches`) | 50% cost reduction for async/non-latency-sensitive work |
| **Server-side tools** | `web_search`, `web_fetch`, `code_execution`, `memory` — Anthropic runs them |
| **Compaction (beta)** | Server-side summarization for conversations near the context window |
| **`metadata`** | `user_id` for abuse/quota tracking — no behavioral effect, just observability |
| **`stop_details` in practice** | Triggering a refusal to inspect the structured stop_details object |
| **MCP integration** | Connect to MCP servers from the API (`mcp_servers` param) |

Each script is self-contained and well under 200 lines — read one, modify, re-run, learn.
