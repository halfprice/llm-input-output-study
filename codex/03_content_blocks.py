"""
03_content_blocks.py — multimodal user input (text + image).

Concepts:
  REQUEST  : when content is multimodal, the user message becomes
             {role: "user", content: [<input_text>, <input_image>, ...]}.
             OpenAI block types you can SEND:
               input_text   — {type:"input_text", text:"..."}
               input_image  — {type:"input_image", image_url:"https://..."}
                              OR {type:"input_image", image_url:"data:image/png;base64,..."}
               input_file   — {type:"input_file", file_id:"file_..."}

  RESPONSE : the assistant's content uses different type strings:
               output_text  — the text block in a message item

Note the naming convention: SEND uses `input_*`, RECEIVE uses `output_*`.
This is in contrast to Anthropic where the same `text` type works both ways.
"""
import base64
import io

from PIL import Image, ImageDraw

from _common import client, MODEL, section, dump


# ============================================================
#  Generate a test PNG (same as the claude script)
# ============================================================
def make_test_image() -> bytes:
    img = Image.new("RGB", (200, 120), color=(245, 240, 230))
    draw = ImageDraw.Draw(img)
    draw.rectangle((20, 20, 180, 100), outline=(180, 80, 60), width=4)
    draw.text((40, 50), "HELLO CODEX", fill=(60, 60, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


img_bytes = make_test_image()
img_b64 = base64.standard_b64encode(img_bytes).decode("ascii")
print(f"Generated test PNG: {len(img_bytes)} bytes")


# ============================================================
#  REQUEST — user message with text + base64 image
# ============================================================
# Base64 images are passed as data: URIs in the image_url field.
# Note: NOT separate `source.type` like Anthropic — the URI scheme tells
# OpenAI it's base64.
section("REQUEST: image (base64) + text")
request = {
    "model": MODEL,
    "input": [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{img_b64}",
                    "detail": "auto",                       # auto | low | high
                },
                {
                    "type": "input_text",
                    "text": "Describe what you see in this image in one short sentence.",
                },
            ],
        }
    ],
}
print("input[0].content = [")
print("  { type='input_image', image_url='data:image/png;base64,...' },")
print("  { type='input_text',  text='Describe what you see...' }")
print("]")


# ============================================================
#  RESPONSE
# ============================================================
section("RESPONSE")
resp = client.responses.create(**request)
print(f"output_text : {resp.output_text!r}")
print(f"\noutput item types: {[i.type for i in resp.output]}")
dump(resp.usage, "usage")


# ============================================================
#  Alternative image sources
# ============================================================
section("OTHER IMAGE SOURCES")
print("""\
URL source — OpenAI fetches the image:
  {"type": "input_image", "image_url": "https://example.com/cat.png"}

File source — file uploaded via /v1/files (returns file_id):
  {"type": "input_image", "file_id": "file_..."}

PDFs / other documents (gpt-4.1 and later support them natively):
  {"type": "input_file", "file_id": "file_..."}
  {"type": "input_file", "file_data": "data:application/pdf;base64,...", "filename": "..."}

`detail` knob (auto | low | high) trades off vision tokens for accuracy:
  - low  : fixed 65 tokens per image, regardless of size
  - high : ~129 tokens per 512×512 tile
  - auto : let OpenAI pick
""")
