from __future__ import annotations

# OpenAI-compatible HTTP client for a local vLLM server. Auto-detects the first available model,
# retries on transient failures, and disables chain-of-thought via chat_template_kwargs.
# LLM_BASE_URL / LLM_MODEL / LLM_API_KEY env vars override defaults.
# Used by email_summaries.py and voyage_summaries.py; wait_for_server used in run_summaries.py.

import os
import time
import urllib.request
from typing import Optional

from openai import OpenAI


DEFAULT_BASE_URL = "http://localhost:8002/v1"
DEFAULT_API_KEY  = "none"


def wait_for_server(base_url: str, timeout_s: int = 120) -> bool:
    models_url = base_url.rstrip("/") + "/models"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(models_url, timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


class LLMClient:
    """
    OpenAI-compatible LLM client configured via environment variables.

    Env vars (all optional):
        LLM_BASE_URL  — API base URL  (default: http://localhost:8002/v1)
        LLM_MODEL     — Model ID      (default: auto-detected from server)
        LLM_API_KEY   — API key       (default: "none" for local servers)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
        resolved_key  = api_key  or os.environ.get("LLM_API_KEY",  DEFAULT_API_KEY)

        self.client = OpenAI(base_url=self.base_url, api_key=resolved_key)

        self.model = (
            model
            or os.environ.get("LLM_MODEL")
            or self._detect_model()
        )

    def _detect_model(self) -> str:
        models = self.client.models.list()
        available = [m.id for m in models.data]
        if not available:
            raise RuntimeError(
                f"LLM server på {self.base_url} har ingen tilgængelige modeller.\n"
                "Sæt LLM_MODEL eller start serveren."
            )
        return available[0]

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2500,
        retries: int = 3,
    ) -> str:
        last_exc = None
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}, "repetition_penalty": 1.15},
                    timeout=60,
                )
                if not response.choices:
                    raise RuntimeError("LLM response has no choices")
                return (response.choices[0].message.content or "").strip()
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
        raise last_exc

    def chat_with_usage(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        retries: int = 3,
        timeout: int = 500,
    ) -> tuple[str, dict[str, int]]:
        last_exc = None
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                    timeout=timeout,
                )
                if not response.choices:
                    raise RuntimeError("LLM response has no choices")

                text = (response.choices[0].message.content or "").strip()
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                }
                return text, usage
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
        raise last_exc
