"""
03_content_blocks.py — content as a list of typed blocks.

Concepts:
  REQUEST  : user-turn `content` can be either a plain string OR a list of
             content blocks. Each block has a `type`. Block types you can
             send in user turns:
               - text
               - image     (source: base64 | url | file)
               - document  (PDF; see 04_-style usage in tools doc)
               - tool_result (only after a tool_use; see 07_)
  RESPONSE : `content` is always a list of blocks. Common reply block types:
               - text
               - thinking            (see 05_)
               - tool_use            (see 07_)
               - server_tool_use     (web_search, code_execution results)

This script demonstrates a multi-block user turn: text + an inline image.
"""
import base64
import io

from PIL import Image, ImageDraw

from _common import client, MODEL, section, dump


# ============================================================
#  Generate a tiny test image so the script is self-contained
# ============================================================
def make_test_image() -> bytes:
    img = Image.new("RGB", (200, 120), color=(245, 240, 230))
    draw = ImageDraw.Draw(img)
    draw.rectangle((20, 20, 180, 100), outline=(180, 80, 60), width=4)
    draw.text((40, 50), "HELLO CLAUDE", fill=(60, 60, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


img_bytes = make_test_image()
img_b64 = base64.standard_b64encode(img_bytes).decode("ascii")
print(f"Generated test PNG: {len(img_bytes)} bytes")


# ============================================================
#  REQUEST — user turn with a list of content blocks
# ============================================================
# A user turn whose content is a LIST can mix block types. Order matters:
# the model reads them top to bottom. A common pattern is [image, text]:
# attach the image, then ask the question about it.
section("REQUEST: image + text in one user turn")
request = {
    "model": MODEL,
    "max_tokens": 200,
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    },
                },
                {
                    "type": "text",
                    "text": "Describe what you see in this image in one short sentence.",
                },
            ],
        }
    ],
}
# Don't dump() the request — it would print the whole base64 blob. Show shape:
print("messages[0].content = [")
print("  { type='image', source={type='base64', media_type='image/png', data=<...>} },")
print("  { type='text',  text='Describe what you see...' }")
print("]")


# ============================================================
#  RESPONSE
# ============================================================
section("RESPONSE")
resp = client.messages.create(**request)
dump(resp.content, "response.content (block list)")
dump(resp.usage, "usage")


# ============================================================
#  Alternative image sources
# ============================================================
# 1) URL source — Anthropic fetches the image:
#      {"type": "image", "source": {"type": "url", "url": "https://..."}}
# 2) File source — file uploaded via Files API (returns file_id):
#      {"type": "image", "source": {"type": "file", "file_id": "file_..."}}
#
# Documents (PDFs) use the same pattern with type="document":
#   {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": ...}}
#   {"type": "document", "source": {"type": "url", "url": "..."}}
#   {"type": "document", "source": {"type": "file", "file_id": "..."}}
section("OTHER SOURCES")
print("Same shape, different .source.type:")
print("  url      — Anthropic fetches the image/PDF")
print("  base64   — inline bytes (what we used above)")
print("  file     — refers to a file uploaded via the Files API")
