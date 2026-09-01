"""
02_system_and_multi_turn.py — system prompts and conversation state.

Concepts:
  REQUEST  : `system` (string OR list of text blocks); messages with
             alternating user/assistant turns to build conversation history.
  RESPONSE : same shape as 01 — but behaviour is shaped by the system prompt
             and prior turns you supply.

Key idea: the Messages API is STATELESS. The server keeps no memory of past
calls. To have a "conversation", you re-send the entire history on every call.
"""
from _common import client, MODEL, section, dump


# ============================================================
#  PART 1 — system as a plain string
# ============================================================
# `system` is an instruction the model treats as authoritative. It's separate
# from `messages` and is conceptually "above" the conversation. Use it for
# persona, output format, hard rules, tools-usage guidance.
section("system as a string")
r1 = client.messages.create(
    model=MODEL,
    max_tokens=128,
    system="Respond only in pirate slang. Never use modern English.",
    messages=[{"role": "user", "content": "How's the weather today?"}],
)
print(r1.content[0].text)


# ============================================================
#  PART 2 — system as a list of text blocks
# ============================================================
# The list form lets you attach metadata to each block — most importantly
# `cache_control` for prompt caching (see 10_prompt_caching.py). Use list
# form when your system prompt is large and shared across many requests.
section("system as a list of text blocks")
r2 = client.messages.create(
    model=MODEL,
    max_tokens=128,
    system=[
        {"type": "text", "text": "You are an expert on Mars geology."},
        {"type": "text", "text": "Always cite the source (Mariner / Viking / Curiosity / Perseverance) when stating a fact."},
    ],
    messages=[{"role": "user", "content": "Name one distinguishing feature of Olympus Mons in one sentence."}],
)
print(r2.content[0].text)


# ============================================================
#  PART 3 — multi-turn conversation (stateless: resend the whole history)
# ============================================================
# Rules for messages[]:
#   - First turn MUST be role="user"
#   - Consecutive same-role turns get merged server-side, but it's clearer to
#     strictly alternate user/assistant
#   - An assistant turn's content can be a string OR the full content list you
#     received back from a previous call
section("multi-turn: re-sending history")

system = "You are a careful tutor. Keep replies to ONE short sentence."
history = [
    {"role": "user", "content": "My favourite colour is sea-foam green."},
]

# Turn 1
r3 = client.messages.create(model=MODEL, max_tokens=128, system=system, messages=history)
assistant_1 = r3.content[0].text
print(f"User      : {history[0]['content']}")
print(f"Assistant : {assistant_1}")

# Append the assistant's reply, then ask a follow-up. The model sees the
# whole history again and "remembers" the colour we mentioned in turn 1.
history.append({"role": "assistant", "content": assistant_1})
history.append({"role": "user", "content": "What colour did I just say I liked?"})

r4 = client.messages.create(model=MODEL, max_tokens=128, system=system, messages=history)
print(f"User      : {history[-1]['content']}")
print(f"Assistant : {r4.content[0].text}")


# ============================================================
#  PART 4 — assistant prefill (older models only) vs the modern alternative
# ============================================================
# Older models (Sonnet 4.5 and earlier) let you "prefill" the assistant's
# response by ending `messages` with role="assistant" — the model then
# continues from that text. On Opus 4.6 / 4.8 and Sonnet 4.6 this 400s.
# The modern replacement is structured outputs (see 09_structured_output.py).
section("assistant prefill — NOT supported on 4.6/4.8")
print("On Opus 4.6 / 4.8 and Sonnet 4.6, ending messages with role='assistant'")
print("returns a 400. Use output_config.format instead (see 09_structured_output.py).")
