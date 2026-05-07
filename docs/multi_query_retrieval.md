# Multi-query retrieval (query reformulation)

Optional retrieval mode that reformulates the incoming question into several search-query variants, retrieves chunks for each variant in parallel, and fuses the results with Reciprocal Rank Fusion (RRF). The goal is better recall on poorly worded, vague, or pronoun-heavy follow-up questions.

Activated per request via a flag. When the flag is off, retrieval behaves exactly as before.

## When to use it

- The user asks a vague or short question ("what about the sugar?", "and him?").
- The user phrases a question in everyday language but the documents use formal maritime terminology — or vice versa.
- A previous turn contains the actual subject (vessel name, port, person) and the new question only refers to it implicitly.

Cost: roughly 3–5× retrieval cost (one embedding + two SQL queries per variant) plus one extra LLM call to generate the variants. Generation cost is unchanged.

## Pipeline

Standard mode (unchanged):

```
query → embed → voyage_key vote → chunk retrieval → neighbor expand → LLM
```

Multi-query mode:

```
query + session history
    → LLM reformulation (4 variants, English, maritime terminology)
    → embed all variants
    → for each variant in parallel: voyage_key vote + chunk retrieval
    → RRF fusion → top_k chunks
    → neighbor expand → LLM
```

The session history (last 3 turns) is fed into the reformulation prompt so pronouns and follow-ups can be resolved into standalone queries.

## Components

| File | Purpose |
| --- | --- |
| `src/02_retrieval/query_expansion/fetch_history.py` | Pulls last N (Q, A) pairs for a `session_id` from `queries` + `generation_logging`. |
| `src/02_retrieval/query_expansion/expand_query.py` | Calls the local vLLM with a reformulation prompt; parses a JSON array of variants; falls back to `[query]` on any failure. |
| `src/02_retrieval/query_expansion/rrf.py` | Reciprocal rank fusion over multiple chunk lists (`rrf_k = 60`). The fused RRF score is stored in `RetrievedChunk.similarity` so downstream code is unchanged. |
| `src/03_generation/multi_query_retrieval.py` | Orchestrates parallel voyage_key + chunk retrieval per variant (ThreadPoolExecutor) and applies RRF. |
| `src/03_generation/run_generation.py` | New `multi_query`, `multi_query_count`, `history_turns` parameters. When `multi_query=True`, the multi-query path is used. |
| `log/log_retrieval.py` | New optional `query_variants` argument; persisted as JSONB in `retrieval_logging.query_variants`. |
| `sql_migrations/0058_retrieval_logging_query_variants.sql` | Adds the `query_variants JSONB` column. |

## How to enable it

### CLI — full pipeline (retrieval + generation)

```bash
python src/03_generation/run_generation.py --query "what happened to the sugar bags" --multi-query
```

Optional: `--multi-query-count 5` to change variant count (default 4).

### CLI — retrieval only (chunk testing, no LLM answer)

For inspecting retrieved chunks without paying for generation:

```bash
python src/02_retrieval/run_retrieve.py --query "what happened to the sugar bags" --multi-query
```

This prints each variant the LLM produced, the union of winning voyage_keys, the fused chunk count and timings, then dumps every expanded chunk as JSON to stdout. Same `--multi-query-count` flag is available. The variants are also written to `retrieval_logging.query_variants` so you can compare runs in SQL afterwards.

Run twice — once with `--multi-query`, once without — and diff the chunk lists to see whether reformulation actually helps for a given question.

### Ground-truth chunk recall test

To measure the actual impact on retrieval quality, the existing chunk-retrieval test in `src/04_testing/step_02_retrieval/chunk_retrieval/run_test.py` now supports `--multi-query`. It iterates over all extractive ground-truth questions, retrieves chunks scoped to the known correct voyage_key (so step 1 errors don't bias the result), and reports recall + MRR.

```bash
# Baseline (single query)
python src/04_testing/step_02_retrieval/chunk_retrieval/run_test.py

# With multi-query reformulation + RRF
python src/04_testing/step_02_retrieval/chunk_retrieval/run_test.py --multi-query
```

Compare the printed `chunk recall` and `MRR` between the two runs to decide whether to enable the flag by default. Run results are also persisted to `retrieval_run_logging` (with the `run_id` printed at the end), so you can compare runs over time.

### API

`POST /chat/message` accepts a new boolean field:

```json
{
  "message": "what happened to the sugar bags",
  "session_id": "…",
  "multi_query": true
}
```

Default is `false`, so existing clients are unaffected.

### Frontend

No UI yet. The chat page always sends `multi_query: false` (since the field is omitted). To wire it up later, add a toggle in `MessageInput.tsx` and pass it through `lib/api.ts → sendMessage`.

## Reformulation prompt — what it produces

Given the user question (and optional history), the LLM is instructed to return a JSON array of 4 strings:

1. The original question rewritten as a standalone, context-resolved English query.
2. A variant using formal maritime / regulatory terminology.
3. A variant in operational / email-style phrasing.
4. A variant focused on the specific entities or events mentioned.

All variants are in English, max 25 words each. Failures (LLM error, malformed JSON) cleanly fall back to `[original query]`, so the request still completes.

## Logging and inspection

Every multi-query run writes the variant list to `retrieval_logging.query_variants` (JSONB) alongside the existing chunks, voyage_keys, and timing data. Useful for debugging "did the reformulation actually help?" — compare retrieved chunks for the same query with and without the flag.

## Apply the migration

```bash
python sql_migrations/migrate.py
```

Then restart the API so the new code is loaded:

```bash
kill <uvicorn-pid> && bash scripts/api.sh
```
