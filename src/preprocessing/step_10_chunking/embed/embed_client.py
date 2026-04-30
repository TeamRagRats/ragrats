from __future__ import annotations

import time
import urllib.request
import openai

DEFAULT_BASE_URL = "http://localhost:8003/v1"
DEFAULT_API_KEY = "none"


def wait_for_server(base_url: str, timeout_s: int = 120) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/models", timeout=5) as resp:
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
