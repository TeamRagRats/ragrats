from __future__ import annotations

# Per-document LLM call. Selects FULL or CLASSIFY mode, runs a pre-flight
# token-budget check against MODEL_MAX_CONTEXT_TOKENS to refuse anything that
# would overflow vLLM, and returns a result dataclass that the main thread
# writes to the DB.

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from step_07_summaries.llm_client import LLMClient
from step_09_llm_extraction.constants import (
    CHARS_PER_TOKEN,
    CLASSIFY_INPUT_TRUNCATE_CHARS,
    CLASSIFY_MAX_TOKENS,
    FULL_MAX_TOKENS,
    MODEL_MAX_CONTEXT_TOKENS,
    SAFETY_MARGIN_TOKENS,
)
from step_09_llm_extraction.db import QueueItem
from step_09_llm_extraction.prompts import (
    CLASSIFY_SYSTEM_PROMPT,
    FULL_SYSTEM_PROMPT,
)


@dataclass
class ExtractionResult:
    sha256: str
    mode: str                              # 'full' | 'classify' | 'skipped'
    status: str                            # 'done' | 'error' | 'skipped'
    document_type: Optional[str] = None
    structured_md: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    error_message: Optional[str] = None
    duration_s: float = 0.0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


def _estimate_tokens(text: str, system_prompt: str) -> int:
    return (len(text) + len(system_prompt)) // CHARS_PER_TOKEN


def _parse_classify_output(text: str) -> tuple[Optional[str], Optional[str]]:
    """Return (document_type, summary) parsed from the two-line CLASSIFY output."""
    doc_type: Optional[str] = None
    summary: Optional[str] = None
    for line in text.splitlines():
        s = line.strip()
        if s.upper().startswith("DOCUMENT_TYPE:"):
            doc_type = s.split(":", 1)[1].strip() or None
        elif s.upper().startswith("SUMMARY:"):
            summary = s.split(":", 1)[1].strip() or None
    return doc_type, summary


def process_single_document(
    item: QueueItem,
    llm: LLMClient,
    classify_threshold: int,
    full_max_tokens: int = FULL_MAX_TOKENS,
    temperature: float = 0.1,
) -> ExtractionResult:
    """Worker entry point. Thread-safe: only reads `item` and `llm`; writes nothing."""
    result = ExtractionResult(sha256=item.sha256, mode="full", status="error")
    result.started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()

    try:
        if classify_threshold == -1 or item.char_count < classify_threshold:
            mode = "full"
            system_prompt = FULL_SYSTEM_PROMPT
            user_prompt = item.markdown
            max_tokens = full_max_tokens
        else:
            mode = "classify"
            system_prompt = CLASSIFY_SYSTEM_PROMPT
            user_prompt = item.markdown[:CLASSIFY_INPUT_TRUNCATE_CHARS]
            max_tokens = CLASSIFY_MAX_TOKENS

        result.mode = mode

        est_input = _estimate_tokens(user_prompt, system_prompt)
        if est_input + max_tokens + SAFETY_MARGIN_TOKENS > MODEL_MAX_CONTEXT_TOKENS:
            # Pre-flight refusal: would overflow vLLM. Mark skipped and bail
            # without an HTTP call.
            result.mode = "classify"
            result.status = "skipped"
            result.error_message = (
                f"pre-flight: estimated {est_input} input tokens + "
                f"{max_tokens} output > model limit {MODEL_MAX_CONTEXT_TOKENS}"
            )
            return result

        text, usage = llm.chat_with_usage(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=1800,
        )

        result.input_tokens = int(usage.get("prompt_tokens", 0))
        result.output_tokens = int(usage.get("completion_tokens", 0))

        if mode == "classify":
            doc_type, summary = _parse_classify_output(text)
            result.document_type = doc_type
            result.structured_md = summary or text
        else:
            result.structured_md = text
            # FULL output starts with "# <Detected Document Type>" per the prompt.
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("#"):
                    result.document_type = s.lstrip("#").strip() or None
                    break

        result.status = "done"
    except Exception as exc:
        result.status = "error"
        result.error_message = f"{type(exc).__name__}: {exc}"

    result.duration_s = round(time.monotonic() - t0, 3)
    result.finished_at = datetime.now(timezone.utc)
    return result
