from __future__ import annotations

# Tier thresholds + worker counts for the LLM extraction step. Sized for the
# DGX Spark / GB10 (128 GB unified memory, ~270 GB/s bandwidth). vLLM runs with
# --max-model-len 131072 so a single server covers all tiers; the worker counts
# below cap concurrent KV-cache pressure.

# Char ranges per size category (chars in docling.markdown).
SMALL_MAX_CHARS  = 30_000
MEDIUM_MAX_CHARS = 95_000
LARGE_MAX_CHARS  = 300_000   # > LARGE_MAX_CHARS => huge => CLASSIFY mode

# Concurrent workers per tier. Tiers are processed sequentially.
WORKERS_BY_TIER: dict[str, int] = {
    "small":  3,
    "medium": 2,
    "large":  1,
    "huge":   1,
}

# Default char-grænse hvor FULL mode skiftes til CLASSIFY mode.
# Matches LARGE_MAX_CHARS by default; can be overridden via --classify-threshold.
DEFAULT_CLASSIFY_THRESHOLD = LARGE_MAX_CHARS

# CLASSIFY mode trims input to this many chars before sending to the LLM.
CLASSIFY_INPUT_TRUNCATE_CHARS = 25_000

# Output budgets.
FULL_MAX_TOKENS     = 8_196
CLASSIFY_MAX_TOKENS = 512

# vLLM model context length. Used by the pre-flight token check to refuse
# requests that would overflow the server (which would otherwise return 400).
MODEL_MAX_CONTEXT_TOKENS = 131_072

# Rough chars-per-token ratio for shipping documents. Used only by the
# pre-flight token estimator; the actual tokenizer would be more accurate but
# this is good enough as a safety guard with the SAFETY_MARGIN_TOKENS buffer.
CHARS_PER_TOKEN = 4

# Tokens reserved on top of estimated input + max_tokens for chat template,
# system prompt overhead, and tokenizer variance.
SAFETY_MARGIN_TOKENS = 400

# Default per-tier batch size; reduced dynamically by _adjust_batch_size when
# GPU/RAM pressure crosses warn/critical thresholds (mirrors run_docling.py).
BATCH_SIZE = 15

# Reuse same warn/critical thresholds as the docling step.
GPU_MEM_WARN_PCT = 80
GPU_MEM_CRITICAL_PCT = 90
RAM_WARN_PCT = 80
RAM_CRITICAL_PCT = 90


def categorize(char_count: int) -> str:
    if char_count <= SMALL_MAX_CHARS:
        return "small"
    if char_count <= MEDIUM_MAX_CHARS:
        return "medium"
    if char_count <= LARGE_MAX_CHARS:
        return "large"
    return "huge"
