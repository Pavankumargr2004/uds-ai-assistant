"""LLM provider abstraction. The LLM is optional: every feature has a deterministic fallback."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional, Protocol

from ..config import Settings


class LLMUnavailable(RuntimeError):
    """Raised when no LLM is configured or the provider cannot be reached."""


class LLMClient(Protocol):
    name: str

    def complete(self, system: str, user: str, json_mode: bool = False) -> str: ...


class NullLLM:
    name = "none"

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        raise LLMUnavailable("no LLM configured (set UDS_LLM_PROVIDER=ollama or openai_compat)")


def _post(url: str, payload: dict, timeout: float, headers: Optional[dict] = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMUnavailable(f"LLM endpoint {url} not reachable: {e}") from e


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self.base_url, self.model, self.timeout = base_url.rstrip("/"), model, timeout
        self.name = f"ollama:{model}"

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        payload = {"model": self.model, "stream": False, "options": {"temperature": 0},
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            payload["format"] = "json"
        return _post(f"{self.base_url}/api/chat", payload, self.timeout)["message"]["content"]


class OpenAICompatClient:
    """Any OpenAI-compatible server (vLLM, llama.cpp server, LM Studio, LocalAI, ...)."""

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 120.0):
        self.base_url, self.model, self.timeout, self.api_key = base_url.rstrip("/"), model, timeout, api_key
        self.name = f"openai_compat:{model}"

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        payload = {"model": self.model, "temperature": 0,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = _post(f"{self.base_url}/chat/completions", payload, self.timeout, headers)
        return data["choices"][0]["message"]["content"]


def get_llm(s: Settings) -> LLMClient:
    if s.llm_provider == "ollama":
        return OllamaClient(s.llm_base_url, s.llm_model, s.llm_timeout_s)
    if s.llm_provider == "openai_compat":
        return OpenAICompatClient(s.llm_base_url, s.llm_model, s.llm_api_key, s.llm_timeout_s)
    return NullLLM()
