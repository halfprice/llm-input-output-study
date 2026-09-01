# Provider Comparison — Claude (Anthropic) vs Codex (OpenAI)

A side-by-side reference for builders moving between providers. Concept-for-concept mapping, captured from live runs against both APIs in this repo. Use the [`claude/`](claude/) and [`codex/`](codex/) scripts to reproduce any of the numbers below.

> **Versions captured:** Claude Opus 4.8 via Anthropic Messages API; gpt-5.6 (`gpt-5.6-sol`, refreshed from the original `gpt-5-2025-08-07` run) via OpenAI Responses API. SDK versions are pinned in [`requirements.txt`](requirements.txt).

---

## TL;DR — the three big differences

1. **Statefulness.** Anthropic is always stateless: every call re-sends the full conversation. OpenAI's Responses API can be stateful via `previous_response_id` — the server keeps history so you only send the new turn.
2. **Response shape.** Anthropic returns a *flat list of content blocks* (`text`, `tool_use`, `thinking`). OpenAI returns a *list of output items* (`reasoning`, `message`, `function_call`) where messages have their own nested `content` array.
3. **Reasoning visibility.** Anthropic's adaptive thinking is optional and per-request. OpenAI's gpt-5.6 reasons by default (billed as output but reported separately), and is now *adaptive* — it occasionally skips reasoning on trivial prompts. Set `reasoning={effort: "none"}` to turn it off entirely (`"minimal"` was removed in 5.6).

---

## Glossary — equivalent terms across providers

| Concept | Anthropic | OpenAI Responses API |
|---|---|---|
| System prompt | `system` | `instructions` |
| Conversation history | `messages` array | `input` array (stateless) OR `previous_response_id` (stateful) |
| Output ceiling | `max_tokens` (required) | `max_output_tokens` (optional) |
| Output text accessor (SDK) | iterate `response.content` | `response.output_text` (one-shot string) |
| Reasoning mode | `thinking: {type: "adaptive"}` | `reasoning: {effort: ...}` |
| Visible reasoning | `thinking.display: "summarized"` | `reasoning.summary: "auto"` |
| Generation termination | `stop_reason` (top-level enum) | `status` + `incomplete_details.reason` |
| Custom stop strings | `stop_sequences` | Not on Responses API (use prompt engineering or Chat Completions) |
| Tool definition | `tools[].input_schema` | `tools[].parameters` (with `type: "function"`) |
| Tool call (in response) | `content[].type === "tool_use"` | `output[].type === "function_call"` |
| Tool result (back to API) | `content[].type === "tool_result"` (in a user turn) | `input[].type === "function_call_output"` |
| Tool-call ID matching | `tool_use.id` ↔ `tool_result.tool_use_id` | `function_call.call_id` ↔ `function_call_output.call_id` |
| Tool args delivery | parsed dict (`block.input`) | JSON **string** (`fc.arguments`, run `json.loads`) |
| Structured output | `output_config.format` | `text.format` |
| Prompt caching | Opt-in via `cache_control` | Automatic; no flag needed |
| Cache hit telemetry | `usage.cache_read_input_tokens` | `usage.input_tokens_details.cached_tokens` |
| Token-count endpoint | `client.messages.count_tokens` | None — use `tiktoken` locally |
| Streaming events | content_block_delta variants | `response.*` event taxonomy (much richer) |
| Image block (input) | `{type:"image", source:{type:"base64", ...}}` | `{type:"input_image", image_url:"data:image/...;base64,..."}` |
| Image block (input via URL) | `{type:"image", source:{type:"url", url:...}}` | `{type:"input_image", image_url:"https://..."}` |
| Text block (output) | `{type:"text", text:...}` | `{type:"output_text", text:...}` |
| Tool-runner auto-loop | `@beta_tool` decorator (built-in) | None on core SDK — use `responses.parse()` loop or OpenAI Agents SDK |

---

## Per-concept comparison

### 1) Basic request

| | Anthropic | OpenAI |
|---|---|---|
| **Endpoint** | `POST /v1/messages` | `POST /v1/responses` |
| **Required body** | `model`, `max_tokens`, `messages` | `model`, `input` |
| **Default response** | Single `content` list with a `text` block | `output` list — *reasoning* item + *message* item |
| **Reasoning by default** | Off (must enable thinking) | **On** for gpt-5.6 (effort=medium), adaptive — 0–50 reasoning_tokens for "Hi" |

**Captured `usage` from "In one sentence, what does the API return?":**

| Field | Claude Opus 4.8 | OpenAI gpt-5 (original run) | OpenAI gpt-5.6-sol (refresh) |
|---|---:|---:|---:|
| input_tokens | 29 | 19 | 19 |
| output_tokens | 61 | 399 | 40 |
| reasoning_tokens (subset of output) | n/a | 320 | 0 |

The gpt-5 response burned ~5× more output tokens than Claude on the same trivial request because reasoning was automatic. gpt-5.6 fixed this: in the captured run it skipped reasoning entirely, and in five re-runs it spent 30–52 reasoning tokens. Pin `reasoning={effort: "none"}` when you want a hard zero.

### 2) System prompt + multi-turn

**Anthropic — always stateless:**
```python
client.messages.create(
    model="claude-opus-4-8", max_tokens=128,
    system="You are a careful tutor.",
    messages=[
        {"role": "user",      "content": "My favourite colour is sea-foam green."},
        {"role": "assistant", "content": "Sea-foam green is lovely!"},
        {"role": "user",      "content": "What colour did I just say I liked?"},
    ],
)
```

**OpenAI — stateless option (same shape):**
```python
client.responses.create(
    model="gpt-5",
    instructions="You are a careful tutor.",                   # not `system`
    input=[
        {"role": "user",      "content": "My favourite colour is sea-foam green."},
        {"role": "assistant", "content": "Sea-foam green is lovely!"},
        {"role": "user",      "content": "What colour did I just say I liked?"},
    ],
)
```

**OpenAI — stateful option (no Anthropic equivalent):**
```python
t1 = client.responses.create(
    model="gpt-5",
    instructions="You are a careful tutor.",
    input="My favourite colour is sea-foam green.",
)
t2 = client.responses.create(
    model="gpt-5",
    previous_response_id=t1.id,                                # <-- chain by reference
    input="What colour did I just say I liked?",
)
```

Trade-offs:

| | Stateless (both providers) | Stateful (OpenAI only) |
|---|---|---|
| Payload size on turn N | grows linearly | tiny — only the new turn |
| State location | client | server (default `store=True`) |
| Portability | works everywhere | OpenAI-only — must rewrite if switching |
| Privacy | data leaves only when you send | history persists on OpenAI side until expiry |

### 3) Vision (text + image content)

The block taxonomy differs more than the underlying concept:

| | Anthropic | OpenAI |
|---|---|---|
| Block type (image, input) | `image` | `input_image` |
| Block type (text, input) | `text` | `input_text` |
| Block type (text, output) | `text` | `output_text` |
| Base64 form | `{type:"image", source:{type:"base64", media_type:"image/png", data:"..."}}` | `{type:"input_image", image_url:"data:image/png;base64,..."}` (URI scheme is the discriminator) |
| URL form | `{type:"image", source:{type:"url", url:"..."}}` | `{type:"input_image", image_url:"https://..."}` |
| Detail knob | none | `detail: "auto" \| "low" \| "high"` (token cost vs accuracy) |

Both providers correctly identified the generated HELLO test PNG in our runs.

### 4) Streaming

**Anthropic event types:** `message_start`, `content_block_start`, `content_block_delta` (with `delta.type` ∈ `text_delta` / `thinking_delta` / `input_json_delta` / `signature_delta` / `citations_delta`), `content_block_stop`, `message_delta`, `message_stop`.

**OpenAI event types** are roughly 10× richer because every nesting level emits add/done events:
- Lifecycle: `response.created`, `response.in_progress`, `response.completed`
- Items: `response.output_item.added`, `response.output_item.done`
- Content parts: `response.content_part.added`, `response.content_part.done`
- Text: `response.output_text.delta`, `response.output_text.done`
- Function calls: `response.function_call_arguments.delta`, `.done`
- Reasoning: `response.reasoning_summary_text.delta`, `.done`

In one captured haiku run, Anthropic produced 1 each of start/stop events + 3 text deltas. OpenAI produced 1 created, 1 in_progress, 2 output_item.added, 1 content_part.added, **17** text_deltas, 1 each of text.done / content_part.done / output_item.done × 2 / response.completed.

Bottom line: more events = more granularity to drive a UI, but more code to handle them. Both SDKs offer a higher-level helper that hides this (`stream.text_stream` / `stream.text_deltas`).

### 5) Thinking / Reasoning

| | Anthropic adaptive thinking | OpenAI reasoning |
|---|---|---|
| Trigger | `thinking={"type": "adaptive"}` | On by default for gpt-5.6; `reasoning.effort = "none"` to suppress (`"minimal"` removed) |
| Depth control | `output_config.effort ∈ low/medium/high/xhigh/max` | `reasoning.effort ∈ none/low/medium/high/xhigh/max` — same ladder as Anthropic now; plus `reasoning.mode ∈ standard/pro` and `reasoning.context ∈ auto/current_turn/all_turns` |
| Visible summary | `thinking.display = "summarized"` | `reasoning.summary = "auto" \| "concise" \| "detailed"` |
| Where reasoning lives in response | `content[].type == "thinking"` block | `output[].type == "reasoning"` item with `summary[]` |
| Reasoning token accounting | Part of output_tokens (no breakdown) | `usage.output_tokens_details.reasoning_tokens` (broken out) |
| Determinism about *whether* it fires | Adaptive — may skip on easy prompts | gpt-5 always invoked it; gpt-5.6 is adaptive too (1 of 6 trivial runs emitted no reasoning item) |

**Captured numbers on the snail puzzle:**

| | Claude Opus 4.8 (adaptive, effort=medium) | gpt-5 (effort=medium, summary=auto) | gpt-5.6-sol (effort=medium, summary=auto) |
|---|---:|---:|---:|
| total output_tokens | 188 | 557 | 114 |
| reasoning_tokens | (not reported separately) | 448 | 65 |
| visible text tokens | 188 | 109 | 49 |

gpt-5.6 spent ~7× fewer reasoning tokens than gpt-5 on the same puzzle and got the same answer. The full 5.6 ladder on this prompt: none=0, low=63, medium=84, high=91, xhigh=118, max=108 reasoning tokens (the ladder is a budget ceiling, not a guarantee — max spent less than xhigh in this run); `mode: "pro"` spent 207 reasoning tokens and inflated input_tokens from 45 to 1973. Always inspect `output_tokens_details.reasoning_tokens` (and `input_tokens` in pro mode) for cost auditing.

### 6) Termination signals

| Outcome | Anthropic | OpenAI |
|---|---|---|
| Normal finish | `stop_reason: "end_turn"` | `status: "completed"` |
| Hit output cap | `stop_reason: "max_tokens"` | `status: "incomplete"` + `incomplete_details.reason: "max_output_tokens"` |
| Custom stop string | `stop_reason: "stop_sequence"`, `stop_sequence` shows which | not available on Responses API |
| Tool wanted | `stop_reason: "tool_use"` (response paused) | `status: "completed"` + a `function_call` item in `output[]` |
| Server-side tool paused | `stop_reason: "pause_turn"` | similar via separate API for hosted tools |
| Safety refusal | `stop_reason: "refusal"` + structured `stop_details` | `status: "incomplete"` + `incomplete_details.reason: "content_filter"` |
| Context window full | `stop_reason: "model_context_window_exceeded"` | `status: "incomplete"` + `incomplete_details.reason: "context_window_exceeded"` |
| Server error mid-call | exception | `status: "failed"` + `response.error` |

Anthropic uses one enum on `stop_reason`. OpenAI splits it into two fields (`status` + `incomplete_details.reason`). Same information, different shape.

### 7) Tool use

The tool-call loop is conceptually identical: define tools → model emits a tool call → you run it → send the result back → loop until done. But the wire details diverge:

| | Anthropic | OpenAI |
|---|---|---|
| Tool definition `schema` field | `input_schema` | `parameters` |
| Tool definition top-level type | (no wrapper) | `type: "function"` (the discriminator) |
| Call appears as | `tool_use` content block in assistant message | `function_call` top-level item in `output[]` |
| Args delivery | parsed dict on `block.input` | JSON string on `fc.arguments` — call `json.loads()` |
| ID to echo back | `block.id` → `tool_result.tool_use_id` | `fc.call_id` → `function_call_output.call_id` |
| Result block | `{type:"tool_result", tool_use_id, content, is_error}` in a **user** turn | `{type:"function_call_output", call_id, output}` in next call's `input` array |
| Error signal | `is_error: true` on the result | no dedicated flag; encode in the `output` string |
| Continuation pattern | resend full `messages` history | either resend `input[]` OR use `previous_response_id` |
| Strict schema mode | `strict: true` (validates inputs) | `strict: true` (validates inputs) |
| Force a tool | `tool_choice={"type":"tool","name":"..."}` | `tool_choice={"type":"function","name":"..."}` |
| Disable parallel calls | `tool_choice.disable_parallel_tool_use: true` | top-level `parallel_tool_calls: false` |
| Auto-loop helper in SDK | `@beta_tool` decorator + `tool_runner` | none — write a 10-line loop around `responses.parse()` (or use the OpenAI Agents SDK) |

In our test run (capital of Japan + sqrt(2)):

- **Claude** took **4 turns** because the sandboxed calculator failed twice (no `round`, no `math` module) before finding `2 ** 0.5`.
- **OpenAI gpt-5** took **3 turns** for the same task; **gpt-5.6-sol** took **4** (it tried `round(math.sqrt(2), 5)`, then `math.sqrt(2)`, then `2 ** 0.5`). With the `responses.parse()` helper (typed Pydantic args) both finished in **2 turns** — the model went straight to `2 ** 0.5`.

### 8) Structured output

Both providers use JSON Schema with similar restrictions. The keypath differs:

| | Anthropic | OpenAI |
|---|---|---|
| Top-level param | `output_config.format` | `text.format` |
| Format type | `{type: "json_schema", schema: {...}}` | `{type: "json_schema", name: "...", schema: {...}, strict: true}` |
| Pydantic helper | `client.messages.parse(output_format=MyClass)` → `.parsed_output` | `client.responses.parse(text_format=MyClass)` → `.output_parsed` |
| `additionalProperties: false` required | Yes (on every object) | Yes (on every object) |
| All fields must be in `required` | No | Yes — use `{"type": ["string", "null"]}` for optional |
| Value-constraint keywords | Most stripped by SDK | Not supported |
| Recursive schemas | Not supported | Not supported |

Both correctly extracted the same invoice schema from the same input email. The OpenAI `required`-all-fields rule is the most common pitfall when porting an Anthropic schema over.

### 9) Prompt caching

| | Anthropic | OpenAI |
|---|---|---|
| How you enable it | Set `cache_control: {type: "ephemeral"}` on a block | **Automatic** — nothing to set |
| Minimum cacheable prefix | ≥ 4096 tokens (Opus 4.8) | ≥ 1024 tokens |
| Granularity | Up to 4 breakpoints — you choose where to cut | Whole prefix only (longest matching) |
| TTL | 5 min default; 1 h via `ttl: "1h"` (write cost 2× instead of 1.25×) | ~5 min (load-dependent) |
| Read price | ~0.1× input price | ~0.5× input price |
| Write price | ~1.25× input price (5 min) or 2× (1 h) | Same as normal input |
| Routing affinity | implicit by prefix hash | implicit; can pin via `prompt_cache_key` |
| Telemetry | `usage.cache_creation_input_tokens` / `cache_read_input_tokens` | `usage.input_tokens_details.cached_tokens` |

Captured cache hit on identical 25K-token reference doc:

| | Claude (run 2) | OpenAI gpt-5 (run 2) | OpenAI gpt-5.6-sol (run 2) |
|---|---:|---:|---:|
| input_tokens (uncached) | 6 | 100 | 16 |
| cached tokens | 25,043 | 13,184 | 13,268 |
| hit rate | ~100% of prefix | 99.2% | 99.9% |

gpt-5.6 responses also report `prompt_cache_retention: "24h"` and a new `input_tokens_details.cache_write_tokens` counter — the 5-minute-TTL caveat from the gpt-5 era no longer applies by default.

Both achieved a clean hit. OpenAI is "free" cheaper to opt into (no code change) but pricier per cached token. For a workload that ships the same large preamble across millions of requests, Anthropic's 0.1× read price wins; for a workload that just wants cheap caching with zero engineering, OpenAI is simpler.

### 10) Token counting

| | Anthropic | OpenAI |
|---|---|---|
| Pre-flight count | `POST /v1/messages/count_tokens` — exact, free | none — count locally with `tiktoken` |
| Library | None needed (network call) | `pip install tiktoken` |
| Accuracy | Exact (server-computed) | Approximate (per-message overhead is encoder-dependent) |
| Use cases | cost estimation, compaction triggers, cache debugging | same |

The local tiktoken approach got us **approx=26**, **actual=28** for the same shopping prompt (identical on gpt-5 and gpt-5.6-sol; both use `o200k_base`) — close but not exact. For exact counts, you have to fire the actual request and read `response.usage.input_tokens` afterwards.

---

## Stylistic differences in default output

Same prompt, same effort level, different "voice":

| Prompt | Claude Opus 4.8 | gpt-5 | gpt-5.6-sol |
|---|---|---|---|
| "Say hello in 5 words." | "Hello, hope you're doing well!" | "Hello there, hope you're well!" | "Hello there, wonderful person today!" |
| "Write a haiku about TCP/IP." | "Packets seek their path— / handshake, then the data flows, / ACK confirms arrival." | "Packets find their way— / handshake whispers, 'I am here.'" | n/a |
| "Write a haiku about JSON." | n/a | "Braces hold their breath / Keys map values, commas pause / Arrays dream in light" | "Curly braces bloom / Keys and values softly flow / Data dreams in strings" |

All fluent. Claude tends to be slightly more concise by default; gpt-5 tended to produce more explanatory prose. gpt-5.6 adds a direct knob for this: `text.verbosity ∈ low/medium/high` (the mutex explanation went from 126 to 424 output tokens between `low` and `high`).

---

## When each provider's shape is the better fit

**Pick Anthropic if you want:**
- A simpler mental model (always stateless, flat content blocks)
- Fine-grained cache control with 4 breakpoints and the lowest read price
- An auto-looping tool runner out of the box
- Adaptive thinking that's free to skip on easy prompts
- An exact server-side token count before sending

**Pick OpenAI if you want:**
- Stateful conversations without managing history client-side
- A richer event taxonomy for streaming UIs (e.g. surface reasoning summary live)
- Automatic caching with zero opt-in
- Pydantic-typed function-call arguments via `responses.parse`
- The largest ecosystem of third-party tooling and integrations

Most production codebases I've seen end up using both — Anthropic for stable, latency-sensitive read-paths and OpenAI for agentic loops where stateful chaining simplifies code.

---

## Adding a third provider — what to watch for

When this study grows to cover Google Gemini, Cohere, Mistral, or others, expect these consistent dimensions to vary:

| Dimension | Why it matters |
|---|---|
| **Stateful vs stateless** | Affects history management and portability |
| **Content block taxonomy** | `text` vs `output_text` vs `parts[].text` — same idea, different keypath |
| **System prompt name** | `system` / `instructions` / `system_instruction` / preamble role |
| **Tool-call shape** | name + args (JSON or parsed?), ID matching scheme, result block name |
| **Termination enum** | One field or two? What values exist? |
| **Reasoning model conventions** | Visible vs hidden, billed separately or not, depth knob name |
| **Caching mechanics** | Opt-in vs automatic, granularity, pricing curve |
| **Streaming event taxonomy** | How many event types, how nested |
| **Structured output keypath** | Where the schema goes, what's enforced |
| **Token counting** | Pre-flight endpoint? Encoder library? Approximate vs exact? |
| **Image source flavors** | base64 / URL / file-id — each provider has subsets |
| **Stop sequences** | Some support them; OpenAI Responses API does not |
| **PDF / document support** | Native or convert-to-image only? |

To extend this repo:
1. Add a top-level `<provider>/` directory mirroring `claude/` and `codex/`.
2. Build `<provider>/_common.py` that loads the key and exposes a `client`.
3. Mirror the script numbering (`01_basic.py` through `11_token_counting.py`) so the per-concept comparison stays apples-to-apples.
4. Append a column to each table in this file. Provider differences will show up cleanly side-by-side.

---

## Related reading in this repo

- [`WALKTHROUGH.md`](WALKTHROUGH.md) — Anthropic Messages API guided tour
- [`TOOL_USE.md`](TOOL_USE.md) — Anthropic tool-use deep dive (wire format, three rules, parallel calls)
- [`claude/`](claude/) — runnable Anthropic scripts (01 through 11)
- [`codex/`](codex/) — runnable OpenAI scripts (01 through 11, same numbering; plus 12 for the gpt-5.6 delta)
