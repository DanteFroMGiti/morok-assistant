from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import urlopen


def available_ollama_models() -> tuple[str, ...]:
    """Read installed model names from the local Ollama service, if it is running."""
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5) as response:
            raw = json.load(response)
    except (OSError, URLError, ValueError):
        return ()
    models = raw.get("models") if isinstance(raw, dict) else None
    if not isinstance(models, list):
        return ()
    return tuple(
        name
        for item in models
        if isinstance(item, dict) and isinstance(name := item.get("name"), str) and name
    )


def ollama_running() -> bool:
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5):
            return True
    except (OSError, URLError):
        return False
