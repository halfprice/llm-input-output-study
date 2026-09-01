# OpenAI Responses API — Hands-on Walkthrough

A guided tour of every type of input and output for the OpenAI Responses API, with real captured runs. The OpenAI counterpart to [`WALKTHROUGH.md`](WALKTHROUGH.md).

**Model used throughout:** `gpt-5.6-sol` (echoed back verbatim in `response.model` — unlike `gpt-5`, which resolved to a dated snapshot `gpt-5-2025-08-07`). This is a refresh of the original gpt-5 study; every captured output below was re-run on gpt-5.6-sol. Section [12](#12--whats-new-in-gpt-56) covers what 5.6 added, and the original gpt-5 numbers are kept where the difference is instructive.

## How to use this project

```bash
# One-time setup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run any script from the project root
.venv/bin/python codex/01_basic.py
.venv/bin/python codex/05_reasoning_effort.py

# Try a different model
OPENAI_MODEL=gpt-5       .venv/bin/python codex/01_basic.py   # the original study model
OPENAI_MODEL=gpt-5-mini  .venv/bin/python codex/01_basic.py
```

The API key lives at `codex/apikey/zhe_study.apikey` (gitignored). `codex/_common.py` loads it, builds the SDK client, and exports `dump` / `section` helpers. The default model is `gpt-5.6-sol`; older gpt-5 models still run but need `reasoning.effort="minimal"` where the scripts now send `"none"`.

Suggested reading order: top to bottom. Each script builds on the previous concepts.

---

## Running with cURL instead

Every section below includes a copy-pasteable cURL command alongside the Python example. Run all cURL commands from the project root so the relative path to the API key works.

The two required headers, present on every request:

```bash
-H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)"
-H "content-type: application/json"
```

Pretty-print with `jq`:
```bash
curl ... | jq
```

**Shell quoting gotcha** — JSON in `-d '...'` is single-quoted, so apostrophes (`don't`, `it's`) inside your prompt and literal newlines in string values both break the parser. Two robust fixes:

```bash
# 1) Heredoc — anything goes inside, including quotes
curl ... -d @- <<'EOF'
{ "model": "gpt-5.6-sol",
  "input": "Don't worry about quotes here!" }
EOF

# 2) Build the body with jq -n — handles any text including multi-line
QUESTION="Write a poem
about cats"
jq -n --arg q "$QUESTION" '{model:"gpt-5.6-sol", input:$q}' \
  | curl ... -d @-
```

---

## Mental model

Every OpenAI Responses API call goes through `POST /v1/responses`. The request body always has `model` and either `input` (string or array) or `previous_response_id`. The response always has `id`, `status`, `output[]`, `output_text`, and `usage`. Tools, reasoning, streaming, structured output, caching — they're all extra fields on the same shape.

```
REQUEST                              RESPONSE
─────────────────────────            ─────────────────────────
model                (required)      id           — unique response ID
input                (required*)     object       — always "response"
instructions         (optional)      model        — dated snapshot served
previous_response_id (optional)      status       — completed/incomplete/...
tools                (optional)      output[]     — list of typed items
tool_choice          (optional)      output_text  — SDK convenience accessor
reasoning            (optional)      usage        — token counts (incl reasoning)
  .effort .summary                     .input_tokens_details.cache_write_tokens (5.6)
  .mode .context (5.6)               incomplete_details — if status=incomplete
text                 (optional)      prompt_cache_retention — "24h" (5.6)
  .format .verbosity (5.6)
max_output_tokens    (optional)      error        — if status=failed
stream               (optional)      tool_usage   — hosted-tool counters (5.6)
store                (optional)
service_tier         (optional)
metadata             (optional)

*input OR previous_response_id must be provided
```

**Output items** are the universal vocabulary. `response.output` is always a *list of typed items* — for almost every call you'll see:

| Item type | When | Carries |
|-----------|------|---------|
| `reasoning` | Usually. gpt-5 always emitted one; gpt-5.6 is adaptive and occasionally skips it on trivial prompts (never at `effort: "none"`) | `.summary` (only populated if `reasoning.summary='auto'`) |
| `message` | Almost always | `.content[]` of `output_text` blocks; `.phase` = `final_answer` or `commentary` (5.6) |
| `function_call` | When a tool is called | `.name`, `.arguments` (JSON string), `.call_id`, `.namespace` (5.6) |
| `custom_tool_call`, `shell_call`, `apply_patch_call`, `tool_search_call`, `program` | New 5.6 tool types — see section 12 | varies |

Notice the asymmetric naming: input uses `input_text` / `input_image`, output uses `output_text`. Echoing a response back as input means converting between these.

---

## 01 — Basic request

**Concept:** the minimum viable request, and every field on the response.

### Input — Python
```python
client.responses.create(
    model="gpt-5.6-sol",
    input="In one sentence: what does the OpenAI Responses API return?",
)
```

### Input — cURL
```bash
curl https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "input": "In one sentence: what does the OpenAI Responses API return?"
  }' | jq
```

### Output (excerpt — actual run)
```json
{
  "id": "resp_0e39d7f563176fa2006a97369754e087d0a0b76c66c717c8b0",
  "object": "response",
  "model": "gpt-5.6-sol",
  "status": "completed",
  "output": [
    {"type": "message", "role": "assistant", "status": "completed", "phase": "final_answer",
     "content": [{
       "type": "output_text",
       "text": "The OpenAI Responses API returns a structured response object containing the model's generated output—such as text, tool calls, or multimodal content—along with metadata and usage details.",
       "annotations": [], "logprobs": []
     }]}
  ],
  "usage": {
    "input_tokens": 19,
    "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
    "output_tokens": 40,
    "output_tokens_details": {"reasoning_tokens": 0},
    "total_tokens": 59,
    "compute_units": null
  },
  "reasoning": {"context": "all_turns", "effort": "medium", "mode": "standard", "summary": null},
  "text": {"format": {"type": "text"}, "verbosity": "medium"},
  "prompt_cache_retention": "24h",
  "service_tier": "default",
  "billing": {"payer": "developer"},
  "tool_usage": {"image_gen": {"...": 0}, "web_search": {"num_requests": 0}},
  "store": true
}
```

For comparison, the same request on the original `gpt-5` returned `output[0]` = a `reasoning` item and `usage.output_tokens: 399` of which `reasoning_tokens: 320`.

### Takeaways
- `output` is **always a list of items**, not a flat text field. Walk it and check `.type` on each.
- `output[0]` is *usually* a `reasoning` item. On gpt-5 it always was. On gpt-5.6 reasoning is adaptive: this captured run had no reasoning item and 0 reasoning tokens, while five re-runs of the same prompt each produced one (30–52 reasoning tokens). Don't index `output[1]` for the message — filter by `.type`.
- Use `response.output_text` for the SDK convenience accessor that flattens text from all message items.
- **Watch the reasoning_tokens.** On gpt-5 this trivial call cost 320 reasoning tokens out of 399 output tokens — ~80% of the bill. gpt-5.6 brought that to 0–52. Set `reasoning={"effort": "none"}` for a guaranteed zero (`"minimal"` no longer exists on 5.6).
- `response.model` echoes `gpt-5.6-sol` verbatim. Older aliases like `gpt-5` resolved to a dated snapshot (`gpt-5-2025-08-07`).
- New in 5.6: `message.phase`, `usage.input_tokens_details.cache_write_tokens`, `prompt_cache_retention`, `reasoning.mode` / `reasoning.context`, `text.verbosity`, `tool_usage`, `billing`. Section 12 goes through them.

---

## 02 — Instructions + multi-turn conversation

**Concept:** `instructions` shapes behavior; conversation can be stateless (resend history) or stateful (`previous_response_id`).

### Input — instructions as a top-level field (Python)
```python
client.responses.create(
    model="gpt-5.6-sol",
    instructions="Respond only in pirate slang. Never use modern English.",
    input="How is the weather today?",
)
```

### Input — instructions (cURL)
```bash
curl https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "instructions": "Respond only in pirate slang. Never use modern English.",
    "input": "How is the weather today?"
  }' | jq -r '.output[] | select(.type=="message") | .content[0].text'
```
**Output:** *"Arrr, what port or city be ye in?"* (gpt-5 was chattier: *"Arr! From what port be ye hailin', matey? Without yer harbor named, me sky-charts be foggy..."*)

### Input — multi-turn, stateless (resend history)
```python
client.responses.create(
    model="gpt-5.6-sol",
    instructions="You are a careful tutor. Keep replies to ONE short sentence.",
    input=[
        {"role": "user",      "content": "My favourite colour is sea-foam green."},
        {"role": "assistant", "content": "Sea-foam green is a lovely, calming shade!"},
        {"role": "user",      "content": "What colour did I just say I liked?"},
    ],
)
```
**Output:** *"You said your favourite colour is sea-foam green."*

### Input — multi-turn, stateful (`previous_response_id`)
This pattern has **no Anthropic equivalent**. OpenAI keeps the conversation server-side; you just chain by response ID.

```python
# Turn 1 — start fresh
t1 = client.responses.create(
    model="gpt-5.6-sol",
    instructions="You are a careful tutor. Keep replies to ONE short sentence.",
    input="My favourite colour is sea-foam green.",
)
# t1.id = "resp_08e0c8d2fed2b6fa006a97369f48e087d0a0ee4a08b46668ae"
# t1 reply: "Sea-foam green is a lovely, calming colour!"

# Turn 2 — no instructions, no history, just chain
t2 = client.responses.create(
    model="gpt-5.6-sol",
    previous_response_id=t1.id,
    input="What colour did I just say I liked?",
)
```
**Output:** *"Sea-foam green."*

### Input — stateful (cURL)
```bash
# Turn 1
RESP=$(curl -s https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{"model":"gpt-5.6-sol","instructions":"You are a careful tutor.","input":"My favourite colour is sea-foam green."}')

PREV_ID=$(echo "$RESP" | jq -r '.id')

# Turn 2 — chain by previous_response_id
curl https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "previous_response_id": "'"$PREV_ID"'",
    "input": "What colour did I just say I liked?"
  }' | jq -r '.output[] | select(.type=="message") | .content[0].text'
```

### Disable server-side storage
By default `store=true` and OpenAI retains the response (that's what enables `previous_response_id`). To opt out:
```python
client.responses.create(model="gpt-5.6-sol", input="...", store=False)
```

### Takeaways
- `instructions` ≈ Anthropic's `system` — a top-level field, NOT a message in `input`.
- Two valid multi-turn patterns: stateless (Anthropic-like, resend everything) or stateful (`previous_response_id`).
- Stateful means smaller payloads but server-side history persistence — set `store=False` for transient calls.

---

## 03 — Multimodal content (text + image)

**Concept:** when content is multimodal, the user message becomes `{role: "user", content: [<input_text>, <input_image>, ...]}`. Block names use the `input_*` / `output_*` convention.

### Input — base64 image (Python)
```python
messages=[{
    "role": "user",
    "content": [
        {
            "type": "input_image",
            "image_url": f"data:image/png;base64,{img_b64}",
            "detail": "auto",   # auto | low | high
        },
        {"type": "input_text", "text": "Describe what you see in this image in one short sentence."},
    ],
}]
```
The script generates a tiny PNG: a red-bordered rectangle on a beige background with "HELLO CODEX".

### Input — URL image (cURL, easiest copyable form)
```bash
curl https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "input": [{
      "role": "user",
      "content": [
        {"type": "input_image", "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/320px-PNG_transparency_demonstration_1.png"},
        {"type": "input_text", "text": "Describe what you see in one sentence."}
      ]
    }]
  }' | jq -r '.output[] | select(.type=="message") | .content[0].text'
```

### Output (actual run on the generated PNG)
```text
A beige rectangle with a red border contains the word "HELLOCODEX."
```
Usage: 52 input tokens (the 1.3 KB PNG plus the text), 20 output tokens, 0 reasoning tokens — gpt-5.6 skipped reasoning on this one.

### Other input sources
```python
# URL — OpenAI fetches the image
{"type": "input_image", "image_url": "https://example.com/cat.png"}

# File reference (after uploading via /v1/files)
{"type": "input_image", "file_id": "file_..."}

# PDFs — gpt-4.1 and later support them natively
{"type": "input_file", "file_id": "file_..."}
{"type": "input_file", "file_data": "data:application/pdf;base64,...", "filename": "x.pdf"}
```

### Takeaways
- Naming asymmetry: `input_image` / `input_text` (you send) vs `output_text` (model sends back).
- Base64 is encoded directly into the `image_url` as a `data:` URI — no separate `source.type` field like Anthropic.
- `detail: low | high | auto` controls vision token cost (low = 65 tokens, high = ~129/tile).

---

## 04 — Streaming

**Concept:** with `stream=True`, the response is a sequence of typed SSE events. OpenAI's event taxonomy is much richer than Anthropic's — every nesting level emits add/done events.

### Input — Python
```python
stream = client.responses.create(
    model="gpt-5.6-sol",
    input="Write a haiku about JSON.",
    stream=True,
)

for event in stream:
    if event.type == "response.output_text.delta":
        print(event.delta, end="", flush=True)
```

### Input — cURL
The `-N` flag disables curl's output buffering so SSE events render live.
```bash
curl -N https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "input": "Write a haiku about JSON.",
    "stream": true
  }'
```

### Output (event trace, actual run)
```text
response.created           → id='resp_0f9c1a6898d3d25e006a9736a7d12887d082f561ac11c5611c'
response.output_item.added → item.type='reasoning', index=0
response.output_item.done  → item.type='reasoning'
response.output_item.added → item.type='message', index=1
response.output_text.delta → 'Cur'
response.output_text.delta → 'ly'
response.output_text.delta → ' braces'
response.output_text.delta → ... (more deltas, omitted)
response.output_text.done  → final text length: 73 chars
response.output_item.done  → item.type='message'
response.completed         → status='completed', output_tokens=121

Event counts: created 1, in_progress 1, output_item.added 2, content_part.added 1,
              output_text.delta 15, output_text.done 1, content_part.done 1,
              output_item.done 2, completed 1

Reassembled text:
Curly braces bloom
Keys and values softly flow
Data dreams in strings
```
The event taxonomy is unchanged from gpt-5. What changed is the bill: the same haiku cost 1128 output tokens on gpt-5 (almost all reasoning) and 121 on gpt-5.6.

### Event types

| Event | When |
|-------|------|
| `response.created` | Once at start — metadata |
| `response.in_progress` | Server began work |
| `response.output_item.added` | A new item (reasoning/message/function_call) began |
| `response.content_part.added` | A new content block inside a message began |
| `response.output_text.delta` | Incremental text — your main event |
| `response.output_text.done` | Text block finished |
| `response.content_part.done` | Content block finished |
| `response.output_item.done` | Item finished |
| `response.function_call_arguments.delta` | Streaming tool call JSON args |
| `response.reasoning_summary_text.delta` | Streaming reasoning summary (when summary=auto) |
| `response.completed` | Final — carries usage & status |
| `error` | Surfaces failures mid-stream |

### Recommended helper
```python
with client.responses.stream(model="gpt-5.6-sol", input="Write a haiku") as stream:
    for text_delta in stream.text_deltas:
        print(text_delta, end="", flush=True)
    final = stream.get_final_response()   # full Response object
```

---

## 05 — Reasoning effort, modes, and visible summaries

**Concept:** reasoning is on by default. You control depth via `effort`, visibility via `summary`, and (new in 5.6) sampling strategy via `mode` and scope via `context`.

### Input — Python
```python
client.responses.create(
    model="gpt-5.6-sol",
    input=(
        "A snail climbs a 30 ft well. Each day it climbs 3 ft, each night "
        "it slips back 2 ft. How many days until it reaches the top? "
        "Think it through."
    ),
    reasoning={"effort": "medium", "summary": "auto"},
)
```

### Input — cURL
```bash
curl https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "input": "A snail climbs a 30 ft well. Each day it climbs 3 ft, each night it slips back 2 ft. How many days until it reaches the top? Think it through.",
    "reasoning": {"effort": "medium", "summary": "auto"}
  }' | jq
```

### Output (actual run, summary captured)
```text
output[0].type = 'reasoning'  →  1 summary block:

summary[0]:
  **Calculating the 28-day climb**
  Alright, I need to calculate the classic 28-day scenario. Each full day
  corresponds to a net gain of 1 foot. ... after 27 nights, I start day 28
  at 27 feet, and the climb reaches 30 feet without any slip.

output[1].type = 'message'
final answer:
  **28 days.**
  After 27 days and nights, the snail is at 27 ft. On day 28, it climbs
  3 ft to reach the 30-ft top and does not slip back.

response.reasoning (echoed back):
  {"context": "all_turns", "effort": "medium", "mode": "standard", "summary": "detailed"}

usage:
  input_tokens                          : 45
  output_tokens                         : 114
  output_tokens_details.reasoning_tokens: 65     ← 57% of output
```
On gpt-5 the same request produced **3** summary blocks and **448** reasoning tokens out of 557 output tokens. Note `summary: "auto"` resolved to `"detailed"` in the echoed `response.reasoning`.

### Output — the full effort ladder (same puzzle, actual run)
```text
effort   reasoning_tk  output_tk  answer
none                0         41  '28 days. After 27 nights, the snail is a...'
low                63        112  '**28 days.** ...'
medium             84        137  '**28 days.** ...'
high               91        138  '**28 days.** ...'
xhigh             118        166  '**28 days.** ...'
max               108        150  '**28 days.** ...'
```
Every level got it right. The ladder is a *ceiling* — on this easy puzzle `max` used fewer tokens than `xhigh`. `effort: "none"` produced **no reasoning item at all** (`[i.type for i in output] == ['message']`).

### Output — `reasoning.mode = "pro"` (actual run)
```text
mode echoed   : pro
answer        : **28 days.** ...
input_tokens  : 1973   ← vs 45 in standard mode
reasoning_tk  : 207
output_tk     : 367
```
Pro mode looks like multi-sample reasoning behind the scenes: the *input* token count is ~44× the prompt size on the same request. Budget for it in both directions.

### Knob reference (gpt-5.6)

| Parameter | Values | Effect |
|-----------|--------|--------|
| `reasoning.effort` | `none` / `low` / `medium` / `high` / `xhigh` / `max` | Reasoning budget (medium is default). `none` = truly off. `minimal` was **removed** — sending it returns `400 unsupported_value`. |
| `reasoning.summary` | `None` / `concise` / `detailed` / `auto` | Visible summary blocks (None is default) |
| `reasoning.mode` | `standard` / `pro` | **New.** `pro` = heavier multi-sample thinking |
| `reasoning.context` | `auto` / `current_turn` / `all_turns` | **New.** How much prior conversation reasoning may consider. `auto` resolved to `all_turns` in our run. |

### Takeaways
- gpt-5 *always* emitted a `reasoning` item, even at `minimal`. gpt-5.6 is adaptive: it may skip reasoning on trivial prompts at `medium`, and never reasons at `none`.
- The effort ladder now matches Anthropic's (`low`…`max`), and `none` matches "thinking off". The two providers have converged here.
- Reasoning tokens are still BILLED AS OUTPUT. Audit `output_tokens_details.reasoning_tokens`, and in `pro` mode audit `input_tokens` too.

---

## 06 — Termination states (status + incomplete_details)

**Concept:** OpenAI uses two fields where Anthropic uses one. `response.status` is the top-level outcome; `response.incomplete_details.reason` explains why if status is `incomplete`.

### Live demonstrations

**`status: "completed"`** — normal completion.
```bash
curl https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "input": "Say hello in 5 words.",
    "reasoning": {"effort": "none"}
  }' | jq '{text:(.output[]|select(.type=="message")|.content[0].text), status, incomplete_details}'
```
```text
{"text": "Hello there, wonderful person today!", "status": "completed", "incomplete_details": null}
```

**`status: "incomplete"`** — output truncated because we capped at 20 tokens.
```bash
curl https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "max_output_tokens": 20,
    "input": "Explain the Internet Protocol in full detail.",
    "reasoning": {"effort": "none"}
  }' | jq '{text:(.output[]?|select(.type=="message")?|.content[0].text), status, incomplete_details, output_tokens:.usage.output_tokens}'
```
```text
{"text": "# Internet Protocol (IP)\n\nThe **Internet Protocol (IP)** is the network-layer", "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output_tokens": 20}
```
With `effort: "none"` all 20 tokens went to visible text (`reasoning_tokens: 0`). With reasoning on, the cap covers reasoning + text, so a tiny cap can leave `output_text` empty.

### Other status / reason values (conceptual)

| Status | `incomplete_details.reason` | Meaning |
|--------|------------------------------|---------|
| `completed` | n/a | Normal finish |
| `incomplete` | `max_output_tokens` | Hit your output cap (output truncated) |
| `incomplete` | `content_filter` | Safety filter blocked output |
| `incomplete` | `max_tool_calls` | Exceeded `max_tool_calls` budget |
| `incomplete` | `context_window_exceeded` | Total context (input+reasoning+output) full |
| `failed` | n/a | Server-side error — see `response.error` |
| `in_progress` | n/a | Only visible mid-stream |

### `function_call` items — the tool-use signal
There's no `tool_use` status. When the model wants a tool, status stays `completed` and you'll see a `function_call` item in `output[]`. See script 07.

---

## 07 — Tool use, manual loop

**Concept:** function calling, manual loop. For the deep-dive (three rules, parallel calls, stateless vs stateful chaining), see [`TOOL_USE.md`](TOOL_USE.md) — it covers Anthropic but the loop concepts are identical.

### Input — define tools (Python)
```python
TOOLS = [
    {
        "type": "function",                        # the discriminator
        "name": "calculator",
        "description": "Evaluate a basic arithmetic expression.",
        "parameters": {                            # NOT input_schema like Anthropic
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {"type": "function", "name": "get_capital", "description": "...", "parameters": {...}, "strict": True},
]
```

### Query
> "What is the capital of Japan, and what is sqrt(2) to 5 decimal places? Use your tools."

### Output — the loop in action (actual run with `previous_response_id`)
```text
--- Turn 1 ---
status            : completed
output item types : ['reasoning', 'function_call', 'function_call']
  function_call → get_capital({"country":"Japan"}) → 'Tokyo'
  function_call → calculator({"expression":"round(math.sqrt(2), 5)"}) → "ERROR: name 'round' is not defined"

--- Turn 2 ---
status            : completed
output item types : ['reasoning', 'function_call']
  function_call → calculator({"expression":"math.sqrt(2)"}) → "ERROR: name 'math' is not defined"

--- Turn 3 ---
status            : completed
output item types : ['reasoning', 'function_call']
  function_call → calculator({"expression":"2 ** 0.5"}) → '1.4142135623730951'

--- Turn 4 ---
status            : completed
output item types : ['message']

FINAL ANSWER:
The capital of Japan is **Tokyo**, and \(\sqrt{2}\) to five decimal places is **1.41421**.
```
gpt-5 did this in 3 turns (it skipped the `round(...)` attempt). gpt-5.6 took 4 — same loop shape, same final answer, one more sandbox error to recover from. Note the final turn has no `reasoning` item: 5.6 decided the wrap-up didn't need any.

### Input — turn 1 (cURL)
```bash
curl https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "input": "What is the weather in Tokyo right now? Use the tool.",
    "tools": [{
      "type": "function",
      "name": "get_weather",
      "description": "Get current weather for a city.",
      "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
        "additionalProperties": false
      },
      "strict": true
    }]
  }' | jq
```
The response will have a `function_call` item with a `call_id` like `call_...`. To continue:

### Input — turn 2 (cURL, chained by `previous_response_id`)
```bash
curl https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "previous_response_id": "<resp_id from turn 1>",
    "input": [{
      "type": "function_call_output",
      "call_id": "<call_id from turn 1>",
      "output": "18°C, light rain, humidity 78%"
    }],
    "tools": [{ ... same tool definition ... }]
  }' | jq
```

### Critical wire-level rules
1. **Tool definitions use `parameters`, not `input_schema`.** Top-level `type: "function"` is the discriminator.
2. **Arguments arrive as JSON STRINGS** on `fc.arguments`. Run `json.loads()` before dispatching.
3. **The matching ID is `call_id`, NOT `id`.** `fc.id` is the item ID; `fc.call_id` is what goes in `function_call_output.call_id`.
4. **Result blocks use `function_call_output`** in the `input` array of the next call (not a "user" role message).
5. **`previous_response_id` lets you skip echoing the prior function_call** — just send the new `function_call_output` items. Stateless alternative: resend the full `input[]` array yourself.

---

## 08 — Pydantic-typed tool args via `responses.parse`

**Concept:** OpenAI doesn't ship a full auto-loop like Anthropic's `@beta_tool`. The closest helper is `responses.parse()` + `pydantic_function_tool()` — typed argument validation with a manual loop you still own.

### Input
```python
from openai import pydantic_function_tool
from pydantic import BaseModel, Field

class Calculator(BaseModel):
    """Evaluate a basic arithmetic expression. Use this for any math."""
    expression: str = Field(..., description="Python-style arithmetic.")

class GetCapital(BaseModel):
    """Look up the capital city of a country."""
    country: str = Field(..., description="Country name in English.")

TOOLS = [pydantic_function_tool(Calculator), pydantic_function_tool(GetCapital)]

resp = client.responses.parse(
    model="gpt-5.6-sol",
    input="What is the capital of Kenya, and what is sqrt(2) to 5 decimal places?",
    tools=TOOLS,
)

for fc in (i for i in resp.output if i.type == "function_call"):
    parsed = fc.parsed_arguments    # Pydantic instance — already validated
    if isinstance(parsed, Calculator):
        ...
```

### Output (actual run)
```text
--- Turn 1 ---
output item types : ['function_call', 'function_call']
  function_call → GetCapital(country='Kenya') → 'Nairobi'
  function_call → Calculator(expression='2 ** 0.5') → '1.4142135623730951'

--- Turn 2 ---
output item types : ['message']

FINAL ANSWER:
The capital of Kenya is **Nairobi**, and \(\sqrt{2}\) to five decimal places is **1.41421**.
```

The parse helper finished the same task in **2 turns** vs the manual loop's 4 (3 on gpt-5) — with strict typed arguments the model went straight to `2 ** 0.5`. Also notice turn 1 had *no* reasoning item: gpt-5.6 fired two parallel tool calls without thinking first.

### Manual loop vs parse helper vs Agents SDK

| | Manual (script 07) | `responses.parse` (script 08) | OpenAI Agents SDK |
|---|---|---|---|
| Schemas | hand-written JSON Schema | Pydantic classes → auto-derived | Pydantic classes |
| Args delivery | JSON string, `json.loads` yourself | typed Pydantic instance on `parsed_arguments` | typed |
| Loop | you write it | you write it | wraps for you |
| Hooks (logging, approval) | trivial to add | trivial to add | harder |
| Install | already there | already there | `pip install openai-agents` |

---

## 09 — Structured output (text.format)

**Concept:** force the response to a JSON schema. The Responses API uses `text.format`; Chat Completions used `response_format` (deprecated for new code).

### Input — Pydantic (Python)
```python
class Invoice(BaseModel):
    invoice_number: str
    customer: str
    items: list[LineItem]
    total_usd: float
    payment_terms: Literal["net_15", "net_30", "due_on_receipt"]

resp = client.responses.parse(             # parse() — not create()
    model="gpt-5.6-sol",
    text_format=Invoice,                   # pass the model class
    input="Extract a structured invoice from: Hey, invoice #A-2391...",
)
invoice: Invoice = resp.output_parsed      # typed instance
```

### Output (actual run)
```text
type(resp.output_parsed) = Invoice
invoice.invoice_number   = 'A-2391'
invoice.customer         = 'Acme Coyote Supplies'
invoice.total_usd        = 6488.0
invoice.payment_terms    = 'net_30'
invoice.items:
  -  12 x 'Rocket sleds' @ $499.0
  - 200 x 'Birdseed (lbs)' @ $2.5
```
(gpt-5 normalised the item names to lowercase singular — `'rocket sled'`, `'birdseed (lb)'`; gpt-5.6 kept the source casing. Same schema, same totals.)

### Input — raw JSON Schema (cURL)
```bash
curl https://api.openai.com/v1/responses \
  -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "input": "Classify: I waited 45 minutes for a cold coffee. Never again.",
    "text": {
      "format": {
        "type": "json_schema",
        "name": "sentiment_classification",
        "schema": {
          "type": "object",
          "properties": {
            "sentiment":  {"type": "string", "enum": ["positive", "neutral", "negative"]},
            "confidence": {"type": "number"},
            "keywords":   {"type": "array", "items": {"type": "string"}}
          },
          "required": ["sentiment", "confidence", "keywords"],
          "additionalProperties": false
        },
        "strict": true
      }
    }
  }' | jq -r '.output[]|select(.type=="message")|.content[0].text' | jq
```

### Output
```json
{
  "sentiment": "negative",
  "confidence": 0.99,
  "keywords": ["waited 45 minutes", "cold coffee", "never again"]
}
```

### Schema rules (gotchas)
- Top-level type MUST be `"object"`.
- Every object MUST have `additionalProperties: false`.
- **Every property MUST be listed in `required`** (stricter than Anthropic). For optional fields, use `{"type": ["string", "null"]}` and accept null in your code.
- No value constraints (min, max, regex, length).
- Up to 5 levels of nesting; up to 100 total properties per schema.

---

## 10 — Prompt caching (automatic)

**Concept:** OpenAI caches input prefixes automatically. There's no `cache_control` marker — just structure your prompt so the prefix is stable, and inspect `usage.input_tokens_details.cached_tokens` to confirm.

### Input — Python
```python
instructions = (
    "You answer questions strictly from the REFERENCE DOCUMENT below.\n\n"
    f"REFERENCE DOCUMENT:\n{big_doc}"       # ~13K tokens of context
)

r = client.responses.create(
    model="gpt-5.6-sol",
    instructions=instructions,
    input="What does the HyperSpec document?",   # only the question varies
    prompt_cache_key="hyperspec-study-v1",        # optional: pin to same cache slot
    reasoning={"effort": "none"},
)
```

### Input — cURL
```bash
DOC=$(printf 'The Common Lisp HyperSpec documents every function, macro, and special operator. %.0s' {1..500})

jq -n --arg doc "$DOC" '{
  model: "gpt-5.6-sol",
  instructions: ("You answer questions strictly from the REFERENCE DOCUMENT below.\n\nREFERENCE DOCUMENT:\n" + $doc),
  input: "What does the HyperSpec document?",
  prompt_cache_key: "hyperspec-study-v1",
  reasoning: {effort: "none"}
}' | curl -s https://api.openai.com/v1/responses \
      -H "authorization: Bearer $(cat codex/apikey/zhe_study.apikey)" \
      -H "content-type: application/json" \
      -d @- | jq '.usage'
```
Run it twice and watch `input_tokens_details.cached_tokens` go from 0 to >0.

### Output (actual two-run sequence)
```text
=== RUN 1 — cold cache ===
input_tokens                              : 13282
input_tokens_details.cached_tokens        : 0       ← cold
output_tokens                             : 21
cache hit rate                            : 0.0%

=== RUN 2 — warm cache (same instructions, different question) ===
input_tokens                              : 13284
input_tokens_details.cached_tokens        : 13268   ← warm
output_tokens                             : 19
cache hit rate                            : 99.9%
```
gpt-5 hit 13,184 of 13,284 (99.2%) on the same doc; gpt-5.6 cached 84 more tokens of the prefix. Every 5.6 response also carries `prompt_cache_retention: "24h"` and a `usage.input_tokens_details.cache_write_tokens` counter (0 in both runs here — writes aren't surfaced for this tier).

### Rules and tips
- Caches the **longest matching prefix**. Anything past the first byte change is recomputed.
- Minimum cacheable prefix: ~1024 tokens (much lower than Anthropic's 4096).
- Retention: responses report `prompt_cache_retention: "24h"` on gpt-5.6 (the gpt-5-era ~5-minute TTL caveat no longer applies by default).
- `prompt_cache_key` is optional — pin related requests (e.g., same user) to the same cache slot for better hit rates.
- Pricing: cached reads are discounted vs full input price (check the current pricing page for gpt-5.6; the gpt-5 rate was ~0.5×, vs Anthropic's ~0.1×).

### Silent invalidators (same as Anthropic)
- `datetime.now()` / UUIDs in `instructions`
- Changing the `tools` array between requests
- Switching models (caches are per-model)
- Non-deterministic JSON serialization in tool definitions

---

## 11 — Token counting (local, with tiktoken)

**Concept:** OpenAI has NO server-side count_tokens endpoint. You count locally with `tiktoken`. It's offline, fast, but approximate for chat-style inputs (per-message overhead varies by encoder).

### Input
```python
import tiktoken

try:
    enc = tiktoken.encoding_for_model("gpt-5.6-sol")  # KeyError: tiktoken doesn't know 5.6 yet
except KeyError:
    enc = tiktoken.get_encoding("o200k_base")       # same encoder as the gpt-4o / gpt-5 family

# Raw string
ids = enc.encode("Hello!")
print(len(ids))                                 # 2

# Chat-style approximation
def count_chat(instructions, messages):
    total = len(enc.encode(instructions or "")) + 4
    for m in messages:
        total += len(enc.encode(m["content"])) + 4
    return total
```

### Output (actual run)
```text
model               : gpt-5.6-sol   (not in tiktoken's table → falls back to o200k_base)
encoder name        : o200k_base
text                : 'Hello!'
tokens              : [13225, 0]
count               : 2

approx input_tokens : 26     ← tiktoken local estimate
actual input_tokens : 28     ← from the actual API response (identical to gpt-5)
```

### Use cases
1. **Cost estimation before send.** `tokens * (price / 1_000_000)` — the script uses gpt-5's $1.25/1M list price as a placeholder; gpt-5.6-sol pricing isn't exposed by the API, check the pricing page.
2. **Conversation compaction trigger.** When approaching context window, compact.
3. **Cache-miss debugging.** If cached_tokens stays 0, count two consecutive prefixes locally — any byte-level drift will show up as a count mismatch.

### vs Anthropic
- Anthropic offers `client.messages.count_tokens(...)` — server-side, exact, free.
- OpenAI offers nothing — `tiktoken` is the de facto local approximation.
- For exact OpenAI counts, just send the request and read `response.usage.input_tokens`.

---

## 12 — What's new in gpt-5.6

**Concept:** everything above is the same shape as gpt-5. This section is the delta, discovered by probing `gpt-5.6-sol` live — an invalid value makes the API list the accepted ones, which is the fastest way to enumerate what a model supports. Script: `codex/12_gpt56_new_features.py`.

### Removed
| What | Result |
|------|--------|
| `reasoning.effort: "minimal"` | `400 unsupported_value` — *"Supported values are: 'none', 'low', 'medium', 'high', 'xhigh', and 'max'."* |
| `temperature` | `400` — *"'temperature' is not supported with this model."* |
| Dated model snapshots | `response.model` is `gpt-5.6-sol` verbatim. Siblings on this key: `gpt-5.6-luna`, `gpt-5.6-terra`. |

### New request knobs

| Parameter | Values | Captured effect |
|-----------|--------|-----------------|
| `reasoning.effort` | adds `none`, `xhigh`, `max` | Section 05 |
| `reasoning.mode` | `standard` / `pro` | Section 05 — pro ≈ multi-sample; `input_tokens` 45 → 1973 |
| `reasoning.context` | `auto` / `current_turn` / `all_turns` | Scope of conversation the reasoning sees; default `all_turns` |
| `text.verbosity` | `low` / `medium` / `high` | "Explain what a mutex is" → **132 / 180 / 443** output tokens |
| `service_tier` | `auto` / `default` / `fast` / `flex` / `priority` | Requesting `fast` came back as `service_tier: "priority"` |
| `include` | adds `reasoning.encrypted_content`, `message.output_text.logprobs`, `web_search_call.action.sources`, … | Opt-in extra payload |
| `context_management` | `[{"type": "compaction", "compact_threshold": N}]` | Accepted silently on a short prompt; server-side compaction for long agent loops |

### New response fields

```json
"output": [{"type": "message", "phase": "final_answer", ...}],
"usage": {
  "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
  "compute_units": null
},
"prompt_cache_retention": "24h",
"billing": {"payer": "developer"},
"tool_usage": {"image_gen": {...}, "web_search": {"num_requests": 0}}
```

**`message.phase`** is the one to wire into a UI. A message emitted *before* a tool call is `"commentary"`; the message that ends the turn is `"final_answer"`:
```text
instructions: "Before calling any tool, tell the user in one sentence what you are about to do."
input:        "What is the weather in Tokyo? Use the tool."

output[0] = message       phase='commentary'   "I'll use the weather tool to check the current temperature in Tokyo."
output[1] = function_call get_weather({"city":"Tokyo"})
```

### New tool types

`tools[].type` now accepts: `function`, `custom`, `namespace`, `tool_search`, `programmatic_tool_calling`, `shell`, `apply_patch`, plus the hosted `code_interpreter`, `file_search`, `web_search_preview`, `image_generation`, `mcp`, `computer` / `computer_use_preview`. Each new one produces its own output item, and each has a matching `*_output` input item you send back.

**`custom` — freeform string arguments (no JSON schema).** Ideal for shell, SQL, DSLs.
```python
tools=[{"type": "custom", "name": "run_bash",
        "description": "Runs a raw bash command string. Pass the raw command text, not JSON."}]
```
```text
output[1] = custom_tool_call  name='run_bash'
            input="find . -maxdepth 1 -type f -printf '%s\t%f\n' | sort -nr\n"
→ reply with {"type": "custom_tool_call_output", "call_id": ..., "output": "..."}
```

**`shell` — the model proposes commands, you run them.**
```python
tools=[{"type": "shell"}]
```
```text
output[0] = shell_call  action={"commands": ["ls -la"], "max_output_length": null, "timeout_ms": null}
→ reply with {"type": "shell_call_output", "call_id": ..., "output": ...}
```

**`apply_patch` — the model emits a structured diff.**
```python
tools=[{"type": "apply_patch"}]
```
```text
output[1] = apply_patch_call  operation={"type": "create_file", "path": "hello.txt", "diff": "+hi\n"}
→ apply it, reply with {"type": "apply_patch_call_output", "call_id": ..., "status": "completed"}
```

**`tool_search` + `defer_loading` — lazy tool catalogs.** Mark tools `defer_loading: true` so their schemas aren't in the prompt; the model searches for what it needs, the server injects the matching definitions, then the call proceeds — all in one response:
```python
tools=[{"type": "tool_search"},
       {**WEATHER_TOOL, "defer_loading": True},
       {**STOCK_TOOL,   "defer_loading": True}]
```
```text
output[0] = reasoning
output[1] = tool_search_call    arguments={"paths": ["get_weather"]}
output[2] = tool_search_output  tools=[<full get_weather definition>]
output[3] = function_call       get_weather({"city":"Tokyo"})
```
(`tool_search` with zero deferred tools is a 400: *"requires at least one deferred tool"*.)

**`namespace` — group function tools under a name.** `function_call` items gain a `namespace` field.
```python
tools=[{"type": "namespace", "name": "weather_ns", "description": "Weather tools", "tools": [WEATHER_TOOL]}]
```
```text
output[0] = function_call  name='get_weather'  namespace='weather_ns'
```

**`programmatic_tool_calling` — the model writes a program that calls your tools.** Requires `allowed_callers: ["programmatic"]` on the function tool (the accepted values are `direct` and `programmatic`); without it the model falls back to ordinary parallel `function_call`s.
```python
tools=[{"type": "programmatic_tool_calling"},
       {**WEATHER_TOOL, "allowed_callers": ["programmatic"]}]
```
```text
output[0] = reasoning
output[1] = program  code=
             const tokyo = await tools.get_weather({city: "Tokyo"});
             const paris = await tools.get_weather({city: "Paris"});
             const lima  = await tools.get_weather({city: "Lima"});
             text(JSON.stringify({tokyo, paris, lima}));
output[2] = function_call  get_weather({"city":"Tokyo"})  status='in_progress'
```
You answer each `function_call` with `function_call_output` as usual; the server resumes the program and emits the next call. The `program` / `program_output` item types exist on the input side for replaying this stateless.

### Input item types the API now accepts
Probing `input[0].type` with a bogus value lists the full vocabulary:
`message`, `reasoning`, `function_call` / `function_call_output`, `custom_tool_call` / `custom_tool_call_output`, `shell_call` / `shell_call_output`, `local_shell_call` / `local_shell_call_output`, `apply_patch_call` / `apply_patch_call_output`, `tool_search_call` / `tool_search_output`, `program` / `program_output`, `additional_tools`, `agent_message`, `multi_agent_call` / `multi_agent_call_output`, `compaction` / `compaction_trigger`, `item_reference`, `mcp_call` / `mcp_list_tools` / `mcp_approval_request` / `mcp_approval_response`, `code_interpreter_call`, `computer_call` / `computer_call_output`, `file_search_call`, `web_search_call`, `image_generation_call`.

The `multi_agent_call`, `agent_message`, and `compaction` items are the ones not covered by any script here — they need a `call_id` + `action` and an `encrypted_content` respectively, and belong to the Agents / long-context workflows in the table below.

### Takeaways
- Migrating from gpt-5: replace `effort: "minimal"` with `"none"` and drop `temperature`. Everything else in scripts 01–11 ran unchanged.
- Reasoning got cheaper and adaptive. Same puzzles, ~7× fewer reasoning tokens, and occasionally none at all.
- The tool surface is now a coding-agent toolkit: `shell`, `apply_patch`, `custom`, `tool_search`, `programmatic_tool_calling`. Each is "model proposes, you execute, you post `*_output`" — the same loop as script 07.
- `message.phase` and `text.verbosity` are the two knobs most likely to change how you render output.

---

## Where to go next

What this study covers: basic request, instructions, vision, streaming, reasoning (incl. 5.6 modes), status/termination, tool use (manual + parse helper), structured output, automatic caching, token counting, and the gpt-5.6 delta (phase, verbosity, custom/shell/apply_patch/tool_search/namespace/programmatic tools).

What's left to explore (say the word and I'll build scripts):

| Concept | What it adds |
|---------|--------------|
| **Stateless mode (`store=False`)** | Privacy-sensitive workloads — no server-side history |
| **Web search tool** | OpenAI's hosted web_search tool (`type: "web_search_preview"`) |
| **Code interpreter tool** | OpenAI's hosted code execution sandbox |
| **File search tool** | Vector store integration |
| **Computer use tool** | OpenAI's CUA preview — browser/desktop control |
| **MCP integration** | Connect to MCP servers from the Responses API |
| **Multi-agent items** | `multi_agent_call` / `agent_message` input items (5.6) |
| **Server-side compaction** | `context_management: [{type: "compaction"}]` on long agent loops (5.6) |
| **Full shell / apply_patch loop** | Execute `shell_call` and `apply_patch_call` locally and post the `*_output` items (5.6) |
| **Background mode** | Long-running responses with `background=True` |
| **Batch API** | 50% cost reduction for non-latency-sensitive work |
| **Files API** | Upload once, reference by `file_id` |
| **Realtime API** | Voice + streaming for real-time apps |

---

## Related reading

- [`WALKTHROUGH.md`](WALKTHROUGH.md) — Anthropic Messages API tour (same structure as this doc)
- [`TOOL_USE.md`](TOOL_USE.md) — Tool-use deep dive (covers Anthropic but the loop concepts apply)
- [`COMPARISON.md`](COMPARISON.md) — side-by-side Anthropic vs OpenAI with the captured numbers from both walkthroughs
- [`codex/`](codex/) — runnable scripts, mirrored numbering with `claude/` (plus `12_gpt56_new_features.py`, which has no Claude counterpart)
