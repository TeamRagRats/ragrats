-- Real BM25 lexical retrieval via ParadeDB's pg_search.
--
-- The existing chunks_text_tsv_gin index (migration 0086) backs ts_rank-based
-- lexical retrieval and stays in place — it's still used by the renamed
-- tsrank/ retriever for A/B comparison. This migration adds a second lexical
-- index using pg_search's Tantivy-backed BM25 (with proper IDF and length
-- normalization), exposed via the @@@ operator and paradedb.score().
--
-- Requires the postgres container to be running paradedb/paradedb (which ships
-- pg_search alongside pgvector). The plain pgvector/pgvector:pg16 image does
-- NOT have pg_search; CREATE EXTENSION will fail there.

CREATE EXTENSION IF NOT EXISTS pg_search;

-- BM25 index over the chunks corpus. The filter columns (strategy, voyage_key,
-- source_type) are included in the index so pg_search can push down the
-- predicates that retrieve_hybrid.py / score_bm25.py use to narrow results,
-- rather than evaluating them in a post-filter step on the heap.
--
-- key_field = chunk_id so paradedb.score(chunk_id) resolves to the BM25 score
-- of the matching row.
--
-- The index covers all four chunk strategies. Other strategies will produce
-- no BM25 hits (the @@@ operator just returns nothing on uncovered rows).
CREATE INDEX IF NOT EXISTS chunks_bm25_idx
    ON chunks
    USING bm25 (chunk_id, text, strategy, voyage_key, source_type)
    WITH (key_field = 'chunk_id');
