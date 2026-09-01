"""
Shared helpers for the codex (OpenAI) study scripts.

- Loads the OpenAI API key from codex/apikey/zhe_study.apikey and exposes a
  ready-to-use `openai.OpenAI` client as `client`.
- `dump(obj)` prints any SDK object as nicely-indented JSON so you can see
  every field the API returned.
- `MODEL` is the default model. Override with the OPENAI_MODEL env var.

Not a learning script — only utilities. Read this once, then ignore.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import openai


def _load_api_key() -> str:
    # Normal env var override wins.
    if key := os.environ.get("OPENAI_API_KEY"):
        return key

    # Otherwise read from the local file.
    keyfile = Path(__file__).parent / "apikey" / "zhe_study.apikey"
    if keyfile.exists():
        return keyfile.read_text().strip()

    raise RuntimeError(
        "No API key. Set OPENAI_API_KEY or put a key at "
        f"{keyfile}"
    )


# Set the env var so the SDK and any subprocesses see it too.
os.environ["OPENAI_API_KEY"] = _load_api_key()

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-sol")

client = openai.OpenAI()


def dump(obj, label: str | None = None) -> None:
    """Pretty-print any SDK object as JSON. Falls back to str() for non-JSON types."""
    if label:
        print(f"\n--- {label} ---")
    if hasattr(obj, "model_dump"):
        data = obj.model_dump()
    elif hasattr(obj, "to_dict"):
        data = obj.to_dict()
    else:
        data = obj
    print(json.dumps(data, indent=2, default=str))


def section(title: str) -> None:
    """Print a section header so multi-part scripts are readable."""
    bar = "=" * (len(title) + 4)
    print(f"\n{bar}\n  {title}\n{bar}")
