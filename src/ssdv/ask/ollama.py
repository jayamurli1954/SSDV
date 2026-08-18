from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.1:8b"


class AskError(Exception):
    """Ollama is down, the model is missing, or the reply is empty."""


def default_model() -> str:
    return os.environ.get("SSDV_OLLAMA_MODEL", DEFAULT_MODEL)


def default_host() -> str:
    return os.environ.get("SSDV_OLLAMA_HOST", DEFAULT_HOST).rstrip("/")


def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    host: str | None = None,
    timeout: float = 180,
) -> str:
    """Call local Ollama /api/chat. No extra pip package."""
    url = f"{host or default_host()}/api/chat"
    payload: dict[str, Any] = {
        "model": model or default_model(),
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise AskError(
            f"Ollama HTTP {exc.code} for model {payload['model']}. {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise AskError(
            "Ollama is not running on "
            f"{host or default_host()}. Start the Ollama app, wait until it is ready, "
            f"then retry. Installed models on this PC include llama3.1:8b and qwen3:8b."
        ) from exc
    message = raw.get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        raise AskError("Ollama returned an empty reply.")
    return text
