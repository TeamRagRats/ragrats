# ts_rank — Hybrid Retrieval (legacy lexical path)

Lexical retrieval via Postgres `ts_rank` over a `tsvector` GIN index. Fused
with the vector retriever using Reciprocal Rank Fusion (RRF) by
`retrieve_hybrid.py`.

**Despite the historical "BM25" naming, this is NOT BM25.** `ts_rank` is a
TF-IDF-style cover-density score — no IDF in BM25's sense, no document-length
normalization, no `k1`/`b` knobs. The proper BM25 path lives in the sibling
`bm25/` folder and uses ParadeDB's `pg_search`. This module is kept for
A/B comparison.

---

## Database — `sql_migrations/0086_chunks_tsvector_all_strategies.sql`

- **Column** `text_tsv tsvector` — `GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED`
  for the four chunk strategies (`context`, `plain`, `late`, `summary`).
- **Index** `chunks_text_tsv_gin` — partial GIN.

Tokenizer is `'simple'` on purpose: the corpus is full of proper nouns
(vessel names, port names, voyage keys) where stemming hurts recall.

## Python — `src/02_retrieval/step_02_chunk_retrieval/tsrank/`

| File | Responsibility |
|---|---|
| `tokenize_query.py` | Normalize raw user input before `to_tsquery`. |
| `score_tsrank.py` | `tsrank_retrieve(conn, query_text, top_k, voyage_keys, source_types, strategies)` — pure SQL, returns `list[RetrievedChunk]` with `similarity = ts_rank`. |
| `__init__.py` | Re-exports `tsrank_retrieve`, `tokenize_query`. |

RRF fusion lives one level up at `step_02_chunk_retrieval/fuse_scores.py` —
it's shared between the tsrank and bm25 lexical paths.

## Sanity check

```sql
EXPLAIN ANALYZE
SELECT chunk_id, ts_rank(text_tsv, to_tsquery('simple', 'demurrage | claim')) AS score
FROM chunks
WHERE strategy IN ('context', 'plain', 'late', 'summary')
  AND text_tsv @@ to_tsquery('simple', 'demurrage | claim')
ORDER BY score DESC LIMIT 5;
```

Look for `Bitmap Index Scan on chunks_text_tsv_gin`. A `Seq Scan` means the
index is broken or stale.
