from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_TIMEOUT = 600.0


class AskError(Exception):
    """Ollama is down, the model is missing, or the reply is empty."""


def default_model() -> str:
    return os.environ.get("SSDV_OLLAMA_MODEL", DEFAULT_MODEL)


def default_host() -> str:
    return os.environ.get("SSDV_OLLAMA_HOST", DEFAULT_HOST).rstrip("/")


def default_timeout() -> float:
    raw = os.environ.get("SSDV_OLLAMA_TIMEOUT", str(int(DEFAULT_TIMEOUT)))
    try:
        return max(30.0, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT


def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    host: str | None = None,
    timeout: float | None = None,
) -> str:
    """Call local Ollama /api/chat. No extra pip package."""
    url = f"{host or default_host()}/api/chat"
    wait = default_timeout() if timeout is None else timeout
    payload: dict[str, Any] = {
        "model": model or default_model(),
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.1, "num_predict": 400},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=wait) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise AskError(
            f"Ollama timed out after {int(wait)}s on {host or default_host()} "
            f"(model {payload['model']}). Keep this running in another window:\n"
            r'  & "C:\Users\Muralidhar\AppData\Local\Programs\Ollama\ollama.exe" serve'
            "\n"
            r'  & "C:\Users\Muralidhar\AppData\Local\Programs\Ollama\ollama.exe" run llama3.1:8b "ok"'
            "\nThen retry the ask. First load of an 8B model can take several minutes."
        ) from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise AskError(
            f"Ollama HTTP {exc.code} for model {payload['model']}. {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise AskError(
            "Ollama is not running on "
            f"{host or default_host()}. Start it with:\n"
            r'  & "C:\Users\Muralidhar\AppData\Local\Programs\Ollama\ollama.exe" serve'
            "\nWait until it is ready, then retry."
        ) from exc
    message = raw.get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        raise AskError("Ollama returned an empty reply.")
    return text
