"""
04_streaming.py — Responses API streaming events.

Concepts:
  REQUEST  : pass stream=True to client.responses.create(...)
             OR use the higher-level client.responses.stream(...) context
             manager that accumulates state for you.
  RESPONSE : a stream of typed events. The Responses API event taxonomy is
             FAR richer than Chat Completions — most useful events:

  Lifecycle:
    response.created                     — once, at the very start
    response.in_progress                 — server has begun work
    response.completed                   — final event, carries the full response

  Per-output-item:
    response.output_item.added           — a new item began (reasoning/message/function_call)
    response.output_item.done            — item finished

  Per-content-block (inside a message item):
    response.content_part.added          — new content block (e.g. an output_text block)
    response.output_text.delta           — incremental text — the main event you'll consume
    response.output_text.done            — text block finished
    response.content_part.done

  Function-call streaming:
    response.function_call_arguments.delta  — partial JSON args
    response.function_call_arguments.done

  Reasoning summary streaming (when reasoning.summary='auto'):
    response.reasoning_summary_part.added
    response.reasoning_summary_text.delta
    response.reasoning_summary_text.done

  Error:
    error                                — surfaces failures mid-stream
"""
from collections import Counter

from _common import client, MODEL, section


# ============================================================
#  Raw event stream
# ============================================================
section("RAW STREAM EVENTS")
event_counts = Counter()
text_chunks = []

stream = client.responses.create(
    model=MODEL,
    input="Write a haiku about JSON.",
    stream=True,
)

for event in stream:
    event_counts[event.type] += 1
    et = event.type

    if et == "response.created":
        print(f"response.created           → id={event.response.id!r}")
    elif et == "response.output_item.added":
        print(f"response.output_item.added → item.type={event.item.type!r}, index={event.output_index}")
    elif et == "response.output_text.delta":
        text_chunks.append(event.delta)
        if len(text_chunks) <= 3:
            print(f"response.output_text.delta → {event.delta!r}")
        elif len(text_chunks) == 4:
            print("response.output_text.delta → ... (more deltas, omitted)")
    elif et == "response.output_text.done":
        print(f"response.output_text.done  → final text length: {len(event.text)} chars")
    elif et == "response.output_item.done":
        print(f"response.output_item.done  → item.type={event.item.type!r}")
    elif et == "response.completed":
        print(f"response.completed         → status={event.response.status!r}, "
              f"output_tokens={event.response.usage.output_tokens}")


# ============================================================
#  Summary
# ============================================================
section("SUMMARY")
print("Event counts:")
for et, n in sorted(event_counts.items()):
    print(f"  {et:42s} {n}")
print(f"\nReassembled text:\n{''.join(text_chunks)}")


# ============================================================
#  Helper: client.responses.stream(...)
# ============================================================
section("HELPER: client.responses.stream(...)")
print("""\
For production code, prefer the context-manager form — it accumulates the
final response for you and exposes a typed text iterator:

  with client.responses.stream(model=MODEL, input="Write a haiku") as stream:
      for text_delta in stream.text_deltas:
          print(text_delta, end="", flush=True)
      final = stream.get_final_response()      # full Response object

The raw iterator (shown above) is most useful when you also need to surface
non-text events live (reasoning summary, function-call arguments, etc.).
""")
