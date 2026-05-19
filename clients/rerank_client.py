from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:8004/v1"
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


class RerankClient:
    """Cross-encoder reranker client for vLLM `--task score` servers.

    Hits the OpenAI-compatible `/v1/rerank` endpoint exposed by vLLM when
    Qwen3-Reranker-8B is served with classifier_from_token=['no','yes'].
    The `openai` SDK does not surface /rerank as a first-class method, so
    we POST via urllib directly.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, api_key: str = DEFAULT_API_KEY):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = self._detect_model()

    def _detect_model(self) -> str:
        req = urllib.request.Request(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        models = payload.get("data") or []
        if not models:
            raise RuntimeError(
                f"Rerank server at {self.base_url} has no models available."
            )
        return models[0]["id"]

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        retries: int = 3,
        timeout: int = 60,
    ) -> list[tuple[int, float]]:
        """Score (query, doc) pairs and return [(original_index, score), ...] sorted desc.

        `top_n` truncates the response server-side; pass None to score every
        document.
        """
        if not documents:
            return []

        body: dict = {"model": self.model, "query": query, "documents": documents}
        if top_n is not None:
            body["top_n"] = top_n
        data = json.dumps(body).encode("utf-8")

        for attempt in range(1, retries + 1):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/rerank",
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                results = payload.get("results") or []
                return [
                    (int(item["index"]), float(item["relevance_score"]))
                    for item in results
                ]
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                if attempt == retries:
                    raise RuntimeError(
                        f"Rerank server returned HTTP {exc.code}: {body}"
                    ) from exc
                time.sleep(attempt * 2)
            except Exception:
                if attempt == retries:
                    raise
                time.sleep(attempt * 2)
        raise RuntimeError("unreachable")
