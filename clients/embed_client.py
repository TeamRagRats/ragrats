from __future__ import annotations

import json
import time
import urllib.request
import openai

DEFAULT_BASE_URL = "http://localhost:8003/v1"
DEFAULT_API_KEY = "none"

DEFAULT_TOKEN_BASE_URL = "http://localhost:8004"


def wait_for_server(base_url: str, timeout_s: int = 120) -> bool:
    deadline = time.monotonic() + timeout_s
    probe_url = f"{base_url.rstrip('/')}/models" if base_url.rstrip("/").endswith("/v1") else f"{base_url.rstrip('/')}/v1/models"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(probe_url, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(5)
    return False


class EmbedClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, api_key: str = DEFAULT_API_KEY):
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key)
        self.model = self._detect_model()

    def _detect_model(self) -> str:
        models = self._client.models.list()
        return models.data[0].id

    def embed(self, texts: list[str], retries: int = 3) -> list[list[float]]:
        for attempt in range(1, retries + 1):
            try:
                response = self._client.embeddings.create(input=texts, model=self.model)
                return [item.embedding for item in response.data]
            except Exception:
                if attempt == retries:
                    raise
                time.sleep(attempt * 2)
        raise RuntimeError("unreachable")


class EmbedTokensClient:
    """Client for vLLM /pooling endpoint configured with pooling_type=ALL.

    Returns per-token hidden state vectors (no pooling), used by late chunking
    to mean-pool over per-message token spans.
    """

    def __init__(self, base_url: str = DEFAULT_TOKEN_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.model = self._detect_model()

    def _detect_model(self) -> str:
        with urllib.request.urlopen(f"{self.base_url}/v1/models", timeout=10) as resp:
            data = json.loads(resp.read())
        return data["data"][0]["id"]

    def embed_tokens(self, text: str, retries: int = 3, timeout_s: int = 300) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": text}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/pooling",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(1, retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    payload = json.loads(resp.read())
                return payload["data"][0]["data"]
            except Exception:
                if attempt == retries:
                    raise
                time.sleep(attempt * 2)
        raise RuntimeError("unreachable")
