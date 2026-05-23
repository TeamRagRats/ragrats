# BM25 — Hybrid Retrieval

Real BM25 lexical retrieval via [ParadeDB's `pg_search`](https://github.com/paradedb/paradedb)
extension. Fused with the vector retriever using Reciprocal Rank Fusion (RRF)
in `retrieve_hybrid.py`. The sibling `tsrank/` folder holds the legacy
`ts_rank`-based lexical path (kept for A/B comparison).

The goal is recall on keyword-heavy queries (vessel names, port names, dates,
voyage keys) where pure embedding similarity sometimes misses an exact match.
Unlike `ts_rank`, BM25 has proper IDF weighting and document-length
normalization, so rare terms count more and long documents don't drown out
shorter ones.

---

## Infrastructure

Requires the Postgres container running `paradedb/paradedb:latest` (a
superset of `pgvector/pgvector:pg16` — pgvector still works as before).

Migration `sql_migrations/0096_pg_search_bm25_index.sql`:
- `CREATE EXTENSION IF NOT EXISTS pg_search;`
- BM25 index `chunks_bm25_idx` over `(chunk_id, text, strategy, voyage_key, source_type)`
  with `key_field='chunk_id'`. Filter columns included so pg_search pushes
  predicates down instead of post-filtering on the heap.

Tokenization is handled inside pg_search (Tantivy), so the Python side just
passes raw user input straight through — no `tokenize_query` step.

## Python — `src/02_retrieval/step_02_chunk_retrieval/bm25/`

| File | Responsibility |
|---|---|
| `score_bm25.py` | `bm25_retrieve(conn, query_text, top_k, voyage_keys, source_types, strategies)` — uses `@@@` + `paradedb.score()`. Returns `list[RetrievedChunk]` with `similarity = BM25 score`. |
| `__init__.py` | Re-exports `bm25_retrieve`. |

RRF fusion lives at `step_02_chunk_retrieval/fuse_scores.py` (shared with
the tsrank path).

## Tuning

BM25 uses Tantivy's defaults `k1=1.2`, `b=0.75`. To retune, drop and recreate
the index with the desired parameters in the `WITH` clause:

```sql
DROP INDEX chunks_bm25_idx;
CREATE INDEX chunks_bm25_idx
    ON chunks
    USING bm25 (chunk_id, text, strategy, voyage_key, source_type)
    WITH (key_field = 'chunk_id');
-- (k1/b tuning lives in field-level config; see pg_search docs for the
-- exact syntax in the version pulled by the current image.)
```

## Sanity check

```sql
SELECT chunk_id, paradedb.score(chunk_id) AS bm25, left(text, 80) AS preview
FROM chunks
WHERE text @@@ 'demurrage claim'
  AND strategy = ANY(ARRAY['context','plain','late','summary'])
ORDER BY bm25 DESC
LIMIT 5;
```

Should return chunks whose text contains "demurrage" and/or "claim", ordered
by BM25.
