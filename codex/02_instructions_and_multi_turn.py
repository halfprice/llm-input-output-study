"""
02_instructions_and_multi_turn.py — system prompt + conversation state.

Concepts:
  REQUEST  :
    `instructions` — OpenAI's name for "system prompt". A TOP-LEVEL field,
                     not a message inside `input`. (Compare: Anthropic uses
                     a `system` parameter; Chat Completions used a message
                     with role='system'.)
    `input`        — string OR array of input items. For multi-turn, the
                     array form lets you include past user/assistant turns.
    `previous_response_id` — Responses API is STATEFUL: pass the prior
                     response.id and OpenAI rehydrates the conversation
                     server-side. You don't resend the history.

Key idea: unlike Anthropic, OpenAI's Responses API can be EITHER stateless
(resend the full input array) OR stateful (chain via previous_response_id).
Default is `store=True`, meaning every response is retained.
"""
from _common import client, MODEL, section, dump


# ============================================================
#  PART 1 — instructions (the "system prompt")
# ============================================================
section("instructions (system prompt equivalent)")
r1 = client.responses.create(
    model=MODEL,
    instructions="Respond only in pirate slang. Never use modern English.",
    input="How is the weather today?",
)
print(r1.output_text)


# ============================================================
#  PART 2 — multi-turn via the stateless pattern (input array)
# ============================================================
# You can also send the full history as an array of typed input items.
# This matches the Anthropic pattern of resending the whole conversation.
# Each item is {role, content} where content is a string (the SDK promotes
# it to the right block type automatically).
section("multi-turn: stateless (resend full input array)")
r2 = client.responses.create(
    model=MODEL,
    instructions="You are a careful tutor. Keep replies to ONE short sentence.",
    input=[
        {"role": "user",      "content": "My favourite colour is sea-foam green."},
        {"role": "assistant", "content": "Sea-foam green is a lovely, calming shade!"},
        {"role": "user",      "content": "What colour did I just say I liked?"},
    ],
)
print(r2.output_text)


# ============================================================
#  PART 3 — multi-turn via the stateful pattern (previous_response_id)
# ============================================================
# The unique-to-OpenAI feature: chain responses by reference. You send
# only the new turn; OpenAI loads the prior conversation server-side.
#
# Trade-offs:
#   ✓  Smaller request payloads (don't resend history)
#   ✓  Easier to wire up — no in-app state management
#   ✗  Server-side state means responses persist on OpenAI by default
#      (store=True). Set store=False if you don't want that.
#   ✗  Less portable — no equivalent in Anthropic / most other APIs.
section("multi-turn: stateful (previous_response_id)")

# Turn 1 — start a fresh conversation
turn1 = client.responses.create(
    model=MODEL,
    instructions="You are a careful tutor. Keep replies to ONE short sentence.",
    input="My favourite colour is sea-foam green.",
)
print(f"Turn 1 response_id : {turn1.id}")
print(f"Turn 1 reply       : {turn1.output_text}")

# Turn 2 — chain off the previous response. Notice: no `instructions`,
# no history. Just the new user message and a reference to the prior turn.
turn2 = client.responses.create(
    model=MODEL,
    previous_response_id=turn1.id,
    input="What colour did I just say I liked?",
)
print(f"Turn 2 response_id : {turn2.id}")
print(f"Turn 2 reply       : {turn2.output_text}")


# ============================================================
#  PART 4 — turning off server-side persistence
# ============================================================
# By default, responses are stored on OpenAI's side (store=True). This is
# what makes previous_response_id work. If you don't want that, opt out:
section("disable server-side storage")
r3 = client.responses.create(
    model=MODEL,
    input="One-word reply: stored or transient?",
    store=False,
)
print(f"reply : {r3.output_text}")
print(f"(Without store=True, you can't reference this response by id later.)")


# ============================================================
#  Comparison sketch
# ============================================================
section("ANTHROPIC vs OPENAI multi-turn")
print("""\
ANTHROPIC:                        OPENAI (Responses API):
  system="..."                      instructions="..."
  messages=[                        input=[                  # stateless form
    {role: user,      content},       {role: user,      content},
    {role: assistant, content},       {role: assistant, content},
    {role: user,      content},       {role: user,      content},
  ]                                 ]
  (always stateless)                OR
                                    previous_response_id="resp_..."   # stateful
                                    input="next user turn"
""")
