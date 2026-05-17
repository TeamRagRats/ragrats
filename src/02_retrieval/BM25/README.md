# BM25 — Hybrid Retrieval

Lexical (BM25-style) retrieval via Postgres `ts_rank`, fused with the existing
vector retriever using Reciprocal Rank Fusion (RRF). Slotted into **step_02**
of the retrieval pipeline. Step_00 (reformulation) and step_01 (voyage_key
voting) are untouched.

The goal is recall on keyword-heavy queries (vessel names, port names, dates,
voyage keys) where pure embedding similarity sometimes misses an exact match.

---

## What's implemented

### Database — `sql_migrations/0081_chunks_tsvector.sql`

Adds a persistent lexical index on `chunks`:

- **Column** `text_tsv tsvector` — `GENERATED ALWAYS AS (...) STORED`.
  Auto-populates `to_tsvector('simple', text)` for `strategy='context'` rows;
  NULL for everything else. No trigger needed; Postgres maintains it on
  every INSERT/UPDATE.
- **Index** `chunks_text_tsv_gin` — partial GIN on `strategy='context'`.

Tokenizer is `'simple'` on purpose: the corpus is full of proper nouns
(vessel names, port names, voyage keys) where stemming hurts recall.

### Python modules — `src/02_retrieval/BM25/`

| File | Responsibility |
|---|---|
| `tokenize_query.py` | Normalize raw user input (strip punctuation, collapse whitespace, lowercase) before `plainto_tsquery`. |
| `score_bm25.py` | `bm25_retrieve(conn, query_text, top_k, voyage_keys, source_types)` — pure SQL, hardcoded `strategy='context'`, returns `list[RetrievedChunk]` with `similarity = ts_rank`. |
| `fuse_scores.py` | `rrf_fuse(vector_results, bm25_results, top_k, rrf_k=60)` — Reciprocal Rank Fusion, deduped by `chunk_id`. |
| `hybrid_retrieve.py` | `hybrid_retrieve_chunks(...)` — orchestrator. `mode='hybrid'` runs both retrievers and fuses; `mode='bm25_only'` skips the vector half. |
| `__init__.py` | Re-exports the four functions above. |

### CLI flags

Three new flags wired into `run_retrieve.py` and both `step_02_retrieval`
test runners (`chunk_retrieval/run_test.py`, `e2e_retrieval/run_test.py`):

| Flag | Effect |
|---|---|
| `--hybrid` | Step_02 fuses vector + BM25 via RRF |
| `--bm25-only` | Step_02 uses BM25 only (diagnostic) |
| `--rrf-k INT` | RRF constant (default 60) |

Without any of these flags the pipeline behaves exactly as before — pure
vector retrieval.

### Query routing

When `--hybrid` is set together with `--reformulate`:

- **BM25** receives the **original** user query (no LLM rewrite — we want
  the raw proper nouns to hit the index).
- **Vector** receives the **reformulated** query's embedding.

Both lists are fused by chunk identity.

---

## How to test that it works

### 1. Migration applied

```sql
SELECT count(*) FROM chunks WHERE text_tsv IS NOT NULL AND strategy = 'context';
-- expected: equal to count(*) FROM chunks WHERE strategy = 'context'
SELECT count(*) FROM chunks WHERE text_tsv IS NOT NULL AND strategy <> 'context';
-- expected: 0
```

### 2. GIN index is actually used (no seq scan on `chunks`)

```sql
EXPLAIN ANALYZE
SELECT chunk_id, ts_rank(text_tsv, plainto_tsquery('simple', 'demurrage claim')) AS score
FROM chunks
WHERE strategy = 'context'
  AND text_tsv @@ plainto_tsquery('simple', 'demurrage claim')
ORDER BY score DESC LIMIT 5;
```

Look for `Bitmap Index Scan on chunks_text_tsv_gin` in the plan. If you see
a `Seq Scan on chunks` instead, the index is broken or stale.

### 3. End-to-end retrieval via the CLI

(Embed server must be running on `http://localhost:8003/v1`.)

```bash
# Baseline (vector only) — current behavior, unchanged
python src/02_retrieval/run_retrieve.py --query "Appaloosa charterparty"

# Hybrid: vector + BM25 fused via RRF
python src/02_retrieval/run_retrieve.py --query "Appaloosa charterparty" --hybrid

# BM25 only (diagnostic — should retrieve chunks that literally contain the term)
python src/02_retrieval/run_retrieve.py --query "Appaloosa charterparty" --bm25-only
```

Sanity checks to apply to the output:

- `--bm25-only` for a vessel name should return ≥1 chunk whose `text` field
  contains that exact name.
- `--hybrid` for a strong semantic query should still include the top hits
  that pure-vector returns — RRF shouldn't displace them entirely.
- `--hybrid` for a keyword-heavy query should pull in chunks that pure-vector
  missed.

### 4. Recall@k against ground truth

```bash
# Vector only (baseline)
python src/04_testing/step_02_retrieval/chunk_retrieval/run_test.py --top-k 20

# Hybrid
python src/04_testing/step_02_retrieval/chunk_retrieval/run_test.py --top-k 20 --hybrid

# BM25 only
python src/04_testing/step_02_retrieval/chunk_retrieval/run_test.py --top-k 20 --bm25-only
```

Same flags exist on `e2e_retrieval/run_test.py` for the full step_01 →
step_02 pipeline. Compare `chunk recall` and `MRR` per category — hybrid
should be ≥ vector on `fact_single` (the keyword-heavy class).

---

## Scope boundaries

- BM25 runs **only against `strategy='context'`** rows. The vector side
  keeps whatever `--strategy` filter the user passes.
- BM25 is only in **step_02**. Step_01 voyage_key voting stays pure vector.
- No new Python dependencies — pure Postgres + stdlib.
- Fusion is **RRF only**. No linear weighting, no score normalization.
- The diagnostic `src/04_testing/.../diagnose/bm25_baseline.py` is unchanged
  and is a separate tool from this retriever.
