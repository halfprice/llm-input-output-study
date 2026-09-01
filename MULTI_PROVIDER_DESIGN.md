# Multi-Provider LLM Design — Building an Agent Across Claude / GPT / Gemini / DeepSeek

Architectural guide for building an agent (Claude-Code-style coding assistant, customer-support bot, research agent) that works across every major LLM provider. The central design problem: every provider exposes a similar idea through subtly different wire formats. How do you abstract that without losing the features that matter?

> **TL;DR:** Don't use a translation library — write your own per-provider adapters against an internal canonical data model, and base that model on Anthropic's content-block taxonomy.

---

## Two strategies for generalizing input

| Approach | What it is | When to pick it |
|---|---|---|
| **Translation layer** (LiteLLM, OpenRouter, OpenAI-compatible adapters) | A library normalizes every provider into one wire format (usually OpenAI Chat Completions). You write one code path. | Throwaway scripts, prototypes, side-projects. **Not for an agent you'll maintain.** |
| **Adapter pattern + canonical internal model** | Define your own provider-agnostic request/response data model. Per-provider adapter classes translate to and from it. | Production agents. Every serious coding agent (Claude Code, Cursor, Aider, Cline, Continue) does this. |

The translation-layer route is fast but trades away every provider-specific feature: Anthropic's 4-breakpoint cache control, OpenAI's `previous_response_id`, Gemini's explicit thinking budgets, DeepSeek's R1 reasoning trace. For a serious agent, you'll end up wanting them all.

```
                       ┌──────────────────────────────┐
                       │   Your Agent (provider-      │
                       │   agnostic loop, tools,      │
                       │   conversation state, UI)    │
                       └─────────────┬────────────────┘
                                     │ canonical Request / Response
                  ┌──────────────────┼──────────────────┬──────────────────┐
                  ▼                  ▼                  ▼                  ▼
          ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
          │ Anthropic    │  │ OpenAI       │  │ Gemini       │  │ DeepSeek /   │
          │ Adapter      │  │ Adapter      │  │ Adapter      │  │ ...          │
          └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
                 ▼                 ▼                 ▼                 ▼
            /v1/messages     /v1/responses    generativelanguage   OpenAI-compat
```

---

## The canonical internal model

Use **Anthropic's content-block taxonomy as your canonical shape** — it's the most expressive, and every other provider's API collapses cleanly into it.

```python
from dataclasses import dataclass, field
from typing import Literal, Protocol, Iterator, Any
from enum import Enum


# ─────────── canonical Request ───────────

@dataclass
class Request:
    model: str                            # "anthropic:claude-opus-4-8", "openai:gpt-5.6-sol", ...
    messages: list["Message"]
    system: str | list["TextBlock"] | None = None
    tools: list["Tool"] = field(default_factory=list)
    tool_choice: "ToolChoice" = "auto"
    thinking: "ThinkingMode" = "off"      # uniform knob; per-provider translation
    structured_output: dict | None = None  # JSON Schema
    max_tokens: int | None = None
    stream: bool = False
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class Message:
    role: Literal["user", "assistant", "tool"]
    content: list["Block"]                 # ALWAYS a list, even for plain text


# ─────────── canonical Block (the content vocabulary) ───────────

@dataclass
class TextBlock:
    type: Literal["text"] = "text"
    text: str = ""


@dataclass
class ImageBlock:
    type: Literal["image"] = "image"
    media_type: str = "image/png"          # mime
    source_type: Literal["base64", "url", "file_id"] = "base64"
    data: str = ""                         # base64 bytes, URL, or file_id


@dataclass
class DocumentBlock:
    type: Literal["document"] = "document"
    media_type: str = "application/pdf"
    source_type: Literal["base64", "url", "file_id"] = "base64"
    data: str = ""


@dataclass
class ToolUseBlock:
    type: Literal["tool_use"] = "tool_use"
    id: str = ""                           # CANONICAL id — adapter fabricates one for Gemini
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)   # ALWAYS parsed (not JSON string)


@dataclass
class ToolResultBlock:
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = ""                  # matches ToolUseBlock.id
    content: str = ""
    is_error: bool = False


@dataclass
class ThinkingBlock:
    type: Literal["thinking"] = "thinking"
    text: str = ""
    signature: str | None = None           # opaque; carry through Anthropic round-trips


Block = TextBlock | ImageBlock | DocumentBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock


# ─────────── canonical Tool definition ───────────

@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict                     # JSON Schema (the kind Anthropic uses)
    strict: bool = False


ToolChoice = Literal["auto", "any", "none"] | dict   # dict for {"type":"tool", "name":"..."}
ThinkingMode = Literal["off", "low", "medium", "high"]


# ─────────── canonical Response ───────────

class FinishReason(Enum):
    DONE = "done"                          # natural completion
    TOOL_CALL_PENDING = "tool_call_pending"
    TRUNCATED = "truncated"                # hit max_tokens or context window
    REFUSED = "refused"                    # safety refusal
    ERROR = "error"


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int = 0              # subset of output_tokens; 0 if not applicable
    cached_input_tokens: int = 0           # subset of input_tokens; 0 if no cache hit


@dataclass
class Response:
    id: str
    model: str                             # dated snapshot as returned by provider
    finish_reason: FinishReason
    content: list[Block]                   # the assistant's message content (canonical blocks)
    usage: Usage
    provider_raw: Any = None               # the original SDK response, for debugging
```

Why this shape works:

- **Tools are uniform.** You write tool definitions once in `Tool`; adapters translate.
- **Tool IDs are uniform.** Even Gemini (which doesn't supply an ID per call) gets one your adapter fabricates.
- **Tool arguments are always parsed dicts.** OpenAI's JSON-string `arguments` gets `json.loads()`'d at the adapter boundary. Your agent loop never deals with raw JSON.
- **`content` is always a list.** Empty messages are an empty list, not None. Mixed text+image is just multiple blocks.
- **`finish_reason` is one enum, five values.** Your loop only needs to decide: keep going, dispatch a tool, surface an error, or stop.

---

## The adapter interface

```python
class ProviderAdapter(Protocol):
    """Three jobs: serialize, deserialize, stream."""

    def to_wire(self, request: Request) -> dict:
        """Canonical Request → provider-specific request body."""

    def from_wire(self, raw: Any) -> Response:
        """Provider-specific response → canonical Response."""

    def stream_events(self, raw_stream: Iterator) -> Iterator["StreamEvent"]:
        """Provider's stream events → canonical events
        (TextDelta / ToolCallStarted / ToolCallArgsDelta / ToolCallFinished /
         ReasoningDelta / Done)."""

    def send(self, request: Request) -> Response:
        """Convenience: to_wire → HTTP → from_wire."""
```

Six canonical streaming events cover every UI need:

| Event | Carries |
|---|---|
| `TextDelta(text)` | a chunk of assistant text |
| `ToolCallStarted(id, name)` | a new tool call has begun |
| `ToolCallArgsDelta(id, json_partial)` | streaming JSON args |
| `ToolCallFinished(id)` | tool call complete |
| `ReasoningDelta(text)` | streaming reasoning summary |
| `Done(finish_reason, usage)` | terminal |

Each provider's much-richer event taxonomy fans into these six.

---

## The 8 differences that will bite you

Ranked by how much pain they cause an agent.

### 1) Tool-call ID semantics — the #1 source of bugs

| Provider | Model emits | You echo back as | Arg delivery |
|---|---|---|---|
| Anthropic | `tool_use.id` (`toolu_...`) | `tool_result.tool_use_id` | parsed dict on `.input` |
| OpenAI | `function_call.call_id` (`call_...`) | `function_call_output.call_id` | **JSON string** on `.arguments` — `json.loads()` |
| Google Gemini | `function_call` part (no per-call ID) | `function_response` part matched by `name` | parsed dict on `.args` |
| DeepSeek (OpenAI-compat) | `tool_calls[].id` | `role: "tool"` msg with `tool_call_id` | JSON string |
| Cohere | `tool_calls[].id` | `tool_results[].call.parameters` | parsed dict |
| Mistral | `tool_calls[].id` | `role: "tool"` msg with `tool_call_id` | JSON string |

**Traps:**
- OpenAI's `id` and `call_id` are different fields. Match on `call_id`.
- Gemini matches by tool *name* — parallel calls to the same tool need special handling (some SDK versions add an `id` field; assume it's missing and synthesize one).
- "Arguments as JSON string" is a footgun — easy to forget to parse and pass the string straight to your tool.

Your canonical `ToolUseBlock` always carries an `id` and `input` is always a parsed dict; the adapter normalizes.

### 2) Statefulness

| Provider | Stateless | Stateful |
|---|---|---|
| Anthropic | always | — |
| OpenAI Responses API | yes (resend `input[]`) | yes (`previous_response_id`) |
| OpenAI Chat Completions | yes | — |
| Google Gemini | yes | SDK-side `startChat` session (no referenceable server ID) |
| DeepSeek / Mistral / Cohere | yes | — |

**For an agent: always operate stateless, even on OpenAI.** Stateful chaining is convenient for a chatbot, but for an agent you want:

- **Reproducibility** — replay a session for debugging.
- **Portability** — swap providers without rewiring conversation state.
- **Branching** — fork at turn N to explore alternatives.
- **Visibility** — see exactly what's in the prompt for caching, cost auditing, safety.

`previous_response_id` makes all four hard.

### 3) Reasoning model semantics

| Provider | Mode | Knob | Visibility | Reasoning tokens reported |
|---|---|---|---|---|
| Anthropic | opt-in adaptive | `thinking: {type: "adaptive"}` + `effort` | `thinking.display: "summarized"` | bundled into output_tokens |
| OpenAI gpt-5.6 | on by default, adaptive | `reasoning.effort: none/low/medium/high/xhigh/max` (+ `mode: standard/pro`) | `reasoning.summary: auto/concise/detailed` | broken out as `reasoning_tokens` |
| Google Gemini 2.5/3 | always on (Pro), tunable (Flash) | `thinkingConfig.thinkingBudget` (token budget) | `thinkingConfig.includeThoughts: true` | broken out |
| DeepSeek R1 | always on, baked in | none — emits in `reasoning_content` then `content` | always visible | broken out (some endpoints) |

**Canonical knob:** expose `thinking: "off" | "low" | "medium" | "high"`. Each adapter translates:
- Anthropic: `off` → omit, others → `{type: "adaptive"}` + `effort=...`
- OpenAI: `off` → `reasoning.effort=none` (gpt-5.6; `minimal` on older gpt-5), others → `effort=low/medium/high`
- Gemini: `off` → `thinkingBudget=0`, others → budget tier
- DeepSeek R1: can't disable — pick a non-R1 model for `off`

**Always surface `usage.reasoning_tokens` separately** in your telemetry. An agent that ignores them silently blows its budget on gpt-5-family models (and in gpt-5.6 `reasoning.mode: "pro"` also multiplies `input_tokens`).

### 4) System prompt position

| Provider | Where it goes |
|---|---|
| Anthropic | `system` (top-level field) |
| OpenAI Responses API | `instructions` (top-level field) |
| OpenAI Chat Completions | a message with `role: "system"` |
| Google Gemini | `systemInstruction` (top-level field) |
| DeepSeek / Mistral | message with `role: "system"` |
| Cohere | `preamble` (top-level field) |

Trivial in the adapter. Mentioned because every developer trips on it once.

### 5) Content block taxonomy

| Concept | Anthropic | OpenAI Responses | Gemini |
|---|---|---|---|
| Text (input) | `text` | `input_text` | `text` |
| Text (output) | `text` | `output_text` | `text` |
| Image (base64) | `{type:"image",source:{type:"base64",media_type,data}}` | `{type:"input_image",image_url:"data:image/...;base64,..."}` | `{inlineData:{mimeType,data}}` |
| Image (URL) | `source:{type:"url"}` | `image_url:"https://..."` | `{fileData:{fileUri,mimeType}}` |
| Document / PDF | `{type:"document",source:...}` | `{type:"input_file",file_id\|file_data}` | `inlineData` with `application/pdf` |
| Tool call (output) | `tool_use` block in message | `function_call` item at `output[]` (not inside a message) | `functionCall` part |
| Tool result (input) | `tool_result` block in user message | `function_call_output` item in `input[]` | `functionResponse` part in user message |

Three things to remember:
1. Gemini wraps everything in `parts[]` not `content[]`.
2. The assistant role is `model` in Gemini.
3. Only OpenAI distinguishes `input_*` from `output_*` block names.

### 6) Termination signals

| Provider | Field(s) | Values |
|---|---|---|
| Anthropic | `stop_reason` | `end_turn` / `max_tokens` / `stop_sequence` / `tool_use` / `pause_turn` / `refusal` / `model_context_window_exceeded` |
| OpenAI Responses | `status` + `incomplete_details.reason` | `completed` / `incomplete:max_output_tokens` / `incomplete:content_filter` / `failed` |
| Gemini | `candidates[].finishReason` | `STOP` / `MAX_TOKENS` / `SAFETY` / `RECITATION` / `OTHER` |
| Cohere | `finish_reason` | `COMPLETE` / `MAX_TOKENS` / `ERROR` / `ERROR_TOXIC` |
| DeepSeek / Mistral / OpenAI Chat | `finish_reason` | `stop` / `length` / `tool_calls` / `content_filter` |

Map everything to the canonical `FinishReason` (DONE / TOOL_CALL_PENDING / TRUNCATED / REFUSED / ERROR). Your agent loop only needs those five.

### 7) Prompt caching

| Provider | Trigger | Granularity | Min prefix | Read price | Write price |
|---|---|---|---|---|---|
| Anthropic | explicit `cache_control` marker | up to 4 breakpoints you place | 4096 tokens | ~0.1× | 1.25× (5m) / 2× (1h) |
| OpenAI | automatic | longest prefix only | ~1024 tokens | ~0.5× | normal |
| Gemini | explicit `CachedContent` API for ≥32K; automatic implicit cache below | one cached prefix object | 32K (explicit) | ~0.25× | normal + storage fee |
| DeepSeek | automatic | longest prefix | small | very cheap | normal |

For an agent: **structure your prompt so the prefix is stable** (instructions → tools → conversation history → new turn). That way automatic caching works on OpenAI/Gemini/DeepSeek, and on Anthropic you opt into `cache_control` on the same boundary. Same prompt structure, three different telemetry fields to track.

Caching is THE single biggest cost optimization for an agent — a coding agent re-sending the same 50K of system+tools+repo-context on every turn will burn 90% of its budget on uncached input if you don't fix this.

### 8) Streaming event taxonomy

| Provider | Event count | Shape |
|---|---|---|
| Anthropic | ~6 types | `message_start`, `content_block_start/delta/stop`, `message_delta`, `message_stop` |
| OpenAI Responses | 30+ types | per-item add/done, per-content-part add/done, text delta/done, function_call_arguments delta/done, reasoning_summary_text delta/done, ... |
| Gemini | few | streaming `GenerateContentResponse` chunks, each carries partial `candidates[]` |
| DeepSeek / OpenAI Chat | few | `delta.content`, `delta.tool_calls[].function.arguments` |

Fan all of these into the six canonical events listed earlier. Your UI never sees provider-specific event types.

---

## Practical advice for an agent like openclaw

1. **Bet on the adapter pattern.** A translation library saves a week and costs six months of paper cuts.

2. **Use Anthropic's content-block model as canonical.** Most expressive; everything else collapses into it. OpenAI → canonical is trickiest because OpenAI puts `function_call` at the top of `output[]` (sibling to `message`) — your adapter has to merge them into one assistant message's `content` list.

3. **Always stateless.** Resend the full message history every turn, even on OpenAI. Portability + reproducibility wins always beat bandwidth savings.

4. **Tool definitions in YOUR schema, not the provider's.** Translate at the adapter boundary. Dispatch logic stays uniform.

5. **One canonical agent loop:**

   ```python
   def run(adapter: ProviderAdapter, system: str, tools: list[Tool], user_message: str) -> str:
       messages = [Message(role="user", content=[TextBlock(text=user_message)])]

       for turn in range(MAX_TURNS):
           response = adapter.send(Request(
               model="<chosen>",
               system=system,
               messages=messages,
               tools=tools,
           ))

           # Always append the assistant turn back — preserves tool_use IDs and thinking signatures
           messages.append(Message(role="assistant", content=response.content))

           if response.finish_reason != FinishReason.TOOL_CALL_PENDING:
               return assemble_text(response.content)

           # Dispatch every tool_use block in parallel; build tool_result blocks
           tool_results = parallel_dispatch([
               b for b in response.content if isinstance(b, ToolUseBlock)
           ])

           # Tool results go in the next user turn — even though they came from your code
           messages.append(Message(role="user", content=tool_results))

       raise RuntimeError("Hit MAX_TURNS without resolving")
   ```

   Provider-agnostic. The adapter is the only thing that knows which API it's talking to.

6. **Surface per-provider usage telemetry** in your canonical `Usage`: `input_tokens`, `output_tokens`, `reasoning_tokens` (0 if N/A), `cached_input_tokens` (0 if N/A). Cost calculation lives in a per-provider pricing table.

7. **Test fixtures per provider.** Every adapter has recorded request/response pairs for each canonical operation (basic call, multi-turn, tool call, tool result, structured output, vision, error). When a provider ships a breaking change, your test suite catches it before users do.

8. **Don't try to abstract everything.** Some things are genuinely per-provider:
   - Anthropic's `pause_turn` for server-side tools.
   - OpenAI's hosted `web_search_preview` tool.
   - Gemini's `googleSearchRetrieval`.
   - DeepSeek R1's `reasoning_content` field.

   Expose these as optional provider-specific extensions; the canonical path doesn't have to cover them.

9. **Keep two model registries:**
   - **Capability registry** (Pydantic / dataclass): per-model max context, max output, supports vision, supports tools, supports reasoning, default reasoning level.
   - **Pricing registry**: per-model input price, output price, cached read price, cached write price.

   Both registries are data-only files you update as new models ship — never hardcoded in the adapter or agent.

10. **Version your adapter shims.** Treat each adapter as an external dependency that can break. When Anthropic ships a new content block type or OpenAI restructures `output[]`, your adapter version bumps and your test fixtures catch the regression.

---

## Reference implementations worth studying

| Project | Language | Pattern | What to learn |
|---|---|---|---|
| **[Aider](https://github.com/Aider-AI/aider)** | Python | Uses LiteLLM under the hood; adds its own abstractions for tool use and edit application | How to retrofit a translation layer with feature-specific adapters above it |
| **[Cline](https://github.com/cline/cline)** | TypeScript (VS Code extension) | Fully self-built adapter layer; supports Anthropic, OpenAI, Gemini, DeepSeek, OpenRouter, local Ollama | The cleanest open-source example of the adapter pattern |
| **[Continue](https://github.com/continuedev/continue)** | TypeScript (VS Code/JetBrains) | Self-built adapter layer | Alternative to Cline; slightly different abstraction shape |
| **[OpenAI Agents SDK](https://github.com/openai/openai-agents-python)** | Python | Higher-level Agent abstraction wrapping the Responses API | What an opinionated single-provider abstraction looks like |
| **[LiteLLM](https://github.com/BerriAI/litellm)** | Python | Pure translation layer; OpenAI Chat Completions as the LCD | Useful to study what's left out when you choose simplicity over depth |
| **[Goose](https://github.com/block/goose)** | Rust | Multi-provider agent with MCP integration | Adapter pattern in a typed systems language |

---

## Forward-looking — adding a new provider

When this study or your agent grows to cover another provider (xAI Grok, Inflection, etc.), expect to vary along these dimensions:

| Dimension | Why it matters |
|---|---|
| Stateful vs stateless | Affects history management and portability |
| Content block taxonomy | `text` vs `output_text` vs `parts[].text` — same idea, different keypath |
| System prompt field name | `system` / `instructions` / `systemInstruction` / `preamble` |
| Tool-call shape | name + args (JSON or parsed?), ID matching scheme, result block name |
| Termination enum | One field or two? What values exist? |
| Reasoning conventions | Visible vs hidden, billed separately or not, depth knob name |
| Caching mechanics | Opt-in vs automatic, granularity, pricing curve |
| Streaming event taxonomy | How many event types, how nested |
| Structured output keypath | Where the schema goes, what's enforced |
| Token counting | Pre-flight endpoint? Encoder library? Approximate vs exact? |
| Image source flavors | base64 / URL / file-id — each provider has subsets |
| Stop sequences | Some support them; OpenAI Responses does not |
| PDF support | Native or convert-to-image only? |

Procedure for adding the adapter:
1. Implement `to_wire`, `from_wire`, `stream_events`.
2. Add the model entries to the capability and pricing registries.
3. Add test fixtures for each canonical operation.
4. Run your agent's standard test suite. Anything that fails is a leaky abstraction — fix the adapter (not the agent).

If you find yourself special-casing the adapter from the agent's perspective, that's a smell — the canonical model should absorb the difference.

---

## Related reading in this repo

- [`WALKTHROUGH.md`](WALKTHROUGH.md) — Anthropic Messages API guided tour with captured runs
- [`CODEX_WALKTHROUGH.md`](CODEX_WALKTHROUGH.md) — OpenAI Responses API guided tour, same shape
- [`TOOL_USE.md`](TOOL_USE.md) — Tool-use deep dive (Anthropic, but the loop concepts apply across providers)
- [`COMPARISON.md`](COMPARISON.md) — Concept-by-concept Anthropic vs OpenAI side-by-side
- [`claude/`](claude/) — Runnable Anthropic scripts (01..11)
- [`codex/`](codex/) — Runnable OpenAI scripts (01..11, mirrored numbering; 12 = gpt-5.6 delta)
