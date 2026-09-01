"""
04_streaming.py — what the wire actually looks like.

Concepts:
  REQUEST  : add `stream=True` to messages.create, OR use the helper
             messages.stream() context manager (recommended).
  RESPONSE : a sequence of Server-Sent Events. You assemble the final
             Message from the deltas.

Stream event types (in roughly the order they appear):
  message_start        — message metadata (id, model, usage so-far)
  content_block_start  — a new block begins (text / thinking / tool_use / ...)
  content_block_delta  — incremental update for the block in progress
                          .delta.type tells you what kind of delta:
                            text_delta         → .text         (plain text)
                            thinking_delta     → .thinking     (reasoning)
                            input_json_delta   → .partial_json (tool input)
                            signature_delta    → .signature    (thinking sig)
                            citations_delta    → .citation     (citations)
  content_block_stop   — the in-progress block is finished
  message_delta        — message-level update (stop_reason lands here)
  message_stop         — final marker

This script uses the raw event iterator so you can see each event type fly by.
For most production code, use `client.messages.stream(...).text_stream` or
`stream.get_final_message()` — much less boilerplate.
"""
from collections import Counter

from _common import client, MODEL, section


# ============================================================
#  Raw event iterator — pass stream=True to messages.create
# ============================================================
section("RAW STREAM EVENTS")
event_counts = Counter()
text_chunks = []

stream = client.messages.create(
    model=MODEL,
    max_tokens=128,
    stream=True,                           # <-- the only change vs 01_basic
    messages=[{"role": "user", "content": "Write a haiku about TCP/IP."}],
)

for event in stream:
    event_counts[event.type] += 1

    if event.type == "message_start":
        print(f"message_start        → id={event.message.id!r}, model={event.message.model!r}")
    elif event.type == "content_block_start":
        print(f"content_block_start  → index={event.index}, block.type={event.content_block.type!r}")
    elif event.type == "content_block_delta":
        d = event.delta
        if d.type == "text_delta":
            text_chunks.append(d.text)
            # show only the first few deltas so output stays readable
            if len(text_chunks) <= 3:
                print(f"content_block_delta  → text_delta {d.text!r}")
            elif len(text_chunks) == 4:
                print("content_block_delta  → ... (more text_deltas, omitted)")
        else:
            print(f"content_block_delta  → {d.type}")
    elif event.type == "content_block_stop":
        print(f"content_block_stop   → index={event.index}")
    elif event.type == "message_delta":
        # `stop_reason` and final `usage` deltas arrive here, not in message_start.
        print(f"message_delta        → stop_reason={event.delta.stop_reason!r}, output_tokens={event.usage.output_tokens}")
    elif event.type == "message_stop":
        print("message_stop         → (end of stream)")


# ============================================================
#  Summary
# ============================================================
section("SUMMARY")
print("Event counts:")
for et, n in event_counts.items():
    print(f"  {et:25s} {n}")
print(f"\nReassembled text:\n{''.join(text_chunks)}")


# ============================================================
#  The high-level helper — what you should actually use
# ============================================================
section("HELPER: client.messages.stream(...)")
print("Recommended for production. It accumulates state for you:\n")
print("  with client.messages.stream(model=MODEL, max_tokens=128,")
print("                              messages=[...]) as stream:")
print("      for text in stream.text_stream:")
print("          print(text, end='', flush=True)")
print("      final = stream.get_final_message()  # full Message object")
print()
print("Use the raw iterator (shown above) only when you need fine control,")
print("e.g. surfacing thinking deltas as they arrive, or capturing tool")
print("input JSON tokens for early validation.")
