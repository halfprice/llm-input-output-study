"""
Shared helpers for the study scripts.

- Loads the API key from claude/apikey/<name>.apikey and exposes a ready-to-use
  `anthropic.Anthropic` client as `client`.
- `dump(obj)` prints any SDK object (Message, Usage, etc.) as nicely-indented
  JSON so you can see every field the API returned.
- `MODEL` is the default model used across the study. Override with the
  ANTHROPIC_MODEL env var if you want to try a different one.

Not a learning script — only utilities. Read this once, then ignore.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic


def _load_api_key() -> str:
    # Allow normal env var override first.
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return key

    # Otherwise read from the local file we created in setup.
    keyfile = Path(__file__).parent / "apikey" / "mingwei.apikey"
    if keyfile.exists():
        return keyfile.read_text().strip()

    raise RuntimeError(
        "No API key. Set ANTHROPIC_API_KEY or put a key at "
        f"{keyfile}"
    )


# Set the env var so the SDK and any subprocesses see it too.
os.environ["ANTHROPIC_API_KEY"] = _load_api_key()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")

client = anthropic.Anthropic()


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
