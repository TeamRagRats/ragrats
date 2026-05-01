from __future__ import annotations

# Per-document LLM call. Selects FULL or CLASSIFY mode, runs a pre-flight
# token-budget check against MODEL_MAX_CONTEXT_TOKENS to refuse anything that
# would overflow vLLM, and returns a result dataclass that the main thread
# writes to the DB.

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from clients.llm_client import LLMClient
from step_08_llm_extraction.constants import (
    CHARS_PER_TOKEN,
    CLASSIFY_INPUT_TRUNCATE_CHARS,
    CLASSIFY_MAX_TOKENS,
    FULL_MAX_TOKENS,
    MIN_CONTENT_CHARS,
    MODEL_MAX_CONTEXT_TOKENS,
    SAFETY_MARGIN_TOKENS,
)

# Strips HTML comments (Docling emits <!-- image --> for figures) and whitespace.
_PLACEHOLDER_RE = re.compile(r"<!--[^>]*-->|\s+")
from step_08_llm_extraction.db import QueueItem
from step_08_llm_extraction.prompts import (
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


def _is_context_overflow_error(exc: Exception) -> bool:
    """Detect vLLM 400 BadRequestError caused by input + max_tokens > context."""
    msg = str(exc).lower()
    return (
        "maximum context length" in msg
        or "max_tokens" in msg and "too large" in msg
        or "input_tokens" in msg
        or "context_length_exceeded" in msg
    )


def _run_classify(
    item: QueueItem,
    llm: LLMClient,
    temperature: float,
    result: ExtractionResult,
) -> None:
    """Run CLASSIFY mode and populate `result`. Raises on hard failure."""
    user_prompt = item.markdown[:CLASSIFY_INPUT_TRUNCATE_CHARS]
    text, usage = llm.chat_with_usage(
        system_prompt=CLASSIFY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=CLASSIFY_MAX_TOKENS,
        timeout=600,
    )
    result.mode = "classify"
    result.input_tokens = int(usage.get("prompt_tokens", 0))
    result.output_tokens = int(usage.get("completion_tokens", 0))
    doc_type, summary = _parse_classify_output(text)
    result.document_type = doc_type
    result.structured_md = summary or text


def process_single_document(
    item: QueueItem,
    llm: LLMClient,
    classify_threshold: int,
    full_max_tokens: int = FULL_MAX_TOKENS,
    temperature: float = 0.1,
) -> ExtractionResult:
    """Worker entry point. Thread-safe: only reads `item` and `llm`; writes nothing.

    Two-stage strategy: try FULL mode for small/medium docs. If pre-flight
    refuses or vLLM returns a context-length 400, fall back to CLASSIFY
    (input truncated to CLASSIFY_INPUT_TRUNCATE_CHARS, ~512-token output) so
    every doc gets *some* structured output.
    """
    result = ExtractionResult(sha256=item.sha256, mode="full", status="error")
    result.started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()

    try:
        real_chars = len(_PLACEHOLDER_RE.sub("", item.markdown))
        if real_chars < MIN_CONTENT_CHARS:
            result.status = "skipped"
            result.error_message = (
                f"insufficient_content: {real_chars} real chars after stripping "
                f"placeholders (min={MIN_CONTENT_CHARS})"
            )
            result.duration_s = round(time.monotonic() - t0, 3)
            result.finished_at = datetime.now(timezone.utc)
            return result

        # Decide initial mode by size threshold.
        use_full = classify_threshold == -1 or item.char_count < classify_threshold

        # Pre-flight: if FULL would overflow context, route straight to CLASSIFY
        # instead of skipping. CLASSIFY truncates input to 25k chars + 512-token
        # output → comfortably fits 32k context.
        if use_full:
            est_input = _estimate_tokens(item.markdown, FULL_SYSTEM_PROMPT)
            if est_input + full_max_tokens + SAFETY_MARGIN_TOKENS > MODEL_MAX_CONTEXT_TOKENS:
                use_full = False

        if use_full:
            result.mode = "full"
            try:
                text, usage = llm.chat_with_usage(
                    system_prompt=FULL_SYSTEM_PROMPT,
                    user_prompt=item.markdown,
                    temperature=temperature,
                    max_tokens=full_max_tokens,
                    timeout=1800,
                )
                result.input_tokens = int(usage.get("prompt_tokens", 0))
                result.output_tokens = int(usage.get("completion_tokens", 0))
                result.structured_md = text
                # FULL output starts with "# <Detected Document Type>".
                for line in text.splitlines():
                    s = line.strip()
                    if s.startswith("#"):
                        result.document_type = s.lstrip("#").strip() or None
                        break
                result.status = "done"
            except Exception as exc:
                if _is_context_overflow_error(exc):
                    # Fall back to CLASSIFY — pre-flight estimate was too loose.
                    _run_classify(item, llm, temperature, result)
                    result.status = "done"
                    result.error_message = "fallback_classify: full overflowed context"
                else:
                    raise
        else:
            _run_classify(item, llm, temperature, result)
            result.status = "done"

    except Exception as exc:
        result.status = "error"
        result.error_message = f"{type(exc).__name__}: {exc}"

    result.duration_s = round(time.monotonic() - t0, 3)
    result.finished_at = datetime.now(timezone.utc)
    return result
