"""Minimal chat client for OpenAI-compatible endpoints (Groq, Gemini, Ollama)."""
from __future__ import annotations

import os
import re
import time
from typing import Protocol

import httpx

# provider -> (base URL, name of the env var holding the key, default model)
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemini-2.5-flash"),
    "ollama": ("http://localhost:11434/v1", None, "llama3.2"),
}


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class ChatLLM:
    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: float = 120):
        self.base_url, self.model, self.api_key, self.timeout = base_url.rstrip("/"), model, api_key, timeout
        self.calls = 0
        self.truncated = 0  # replies cut off by the length limit: counted so they are never silent

    def complete(self, system: str, user: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": 6000,
        }
        if "gpt-oss" in self.model:
            # reasoning models think before answering; at the default effort they can spend the whole
            # reply budget thinking and return an empty answer, so they are asked to think briefly
            body["reasoning_effort"] = os.getenv("REASONING_EFFORT", "low")
        r = None
        for attempt in range(10):
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
            if r.status_code == 429 and ("per day" in r.text or "PerDay" in r.text):  # daily quota: waiting minutes will not help
                raise RuntimeError("Daily token quota of the model provider is used up: " + r.text[:300])
            if r.status_code in (429, 500, 502, 503):  # rate limit or transient error: back off and retry
                time.sleep(min(float(r.headers.get("retry-after", 2 ** attempt)), 90) + 1)
                continue
            r.raise_for_status()
            self.calls += 1
            choice = r.json()["choices"][0]
            if choice.get("finish_reason") == "length":
                self.truncated += 1
            content = choice["message"].get("content") or ""
            # some reasoning models put their thinking in the reply: keep only the answer
            return re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
        r.raise_for_status()
        raise RuntimeError("LLM request failed after retries")


def from_env() -> ChatLLM:
    provider = os.getenv("BANKRAG_PROVIDER", "groq").lower()
    if provider not in PROVIDERS:
        raise SystemExit(f"Unknown BANKRAG_PROVIDER '{provider}'. Choose one of: {', '.join(PROVIDERS)}")
    base_url, key_var, default_model = PROVIDERS[provider]
    key = os.getenv(key_var) if key_var else None
    if key_var and not key:
        raise SystemExit(f"{key_var} is not set. Copy .env.example to .env and add your key.")
    return ChatLLM(base_url, os.getenv("BANKRAG_MODEL") or default_model, key)
