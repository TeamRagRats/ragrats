from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import openai

DEFAULT_BASE_URL = "http://localhost:8004/v1"
DEFAULT_API_KEY = "none"

_TASK = "Given a shipping operations query, retrieve relevant passages that answer the query"
_SYSTEM = (
    'Judge whether the Document meets the requirements based on the Query and the Instruct provided. '
    'Note only output a single token "yes" or "no".'
)


class RerankClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, api_key: str = DEFAULT_API_KEY):
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key)
        self.model = self._client.models.list().data[0].id

    def _score_one(self, query: str, document: str, retries: int = 3) -> float:
        user_prompt = f"<Instruct>: {_TASK}\n<Query>: {query}\n<Document>: {document}"
        for attempt in range(1, retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=1,
                    logprobs=True,
                    top_logprobs=20,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
                content_logprobs = resp.choices[0].logprobs.content
                if not content_logprobs:
                    return 0.0
                for lp in content_logprobs[0].top_logprobs:
                    if lp.token.strip().lower() == "yes":
                        return math.exp(lp.logprob)
                return 0.0
            except Exception:
                if attempt == retries:
                    return 0.0
                time.sleep(attempt * 2)
        return 0.0

    def score(self, query: str, documents: list[str], workers: int = 8) -> list[float]:
        """Score all documents against the query in parallel."""
        scores: list[float] = [0.0] * len(documents)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._score_one, query, doc): i
                for i, doc in enumerate(documents)
            }
            for future in as_completed(futures):
                scores[futures[future]] = future.result()
        return scores
