-- Recreate the per-question retrieval test logging tables so every tested
-- question records the full basis for checking its answer: the question text,
-- expected target, the retrieved chunk metadata, and the exact flags the test
-- ran with. FKs point at the canonical `ground_truth` (migration 0089, UUID pk);
-- the old tables still referenced the dropped ground_truth_v3.
--
-- chunks: JSONB array of retrieved-chunk metadata (no text; look up by chunk_id
--         in the chunks table). Shape: [{rank, chunk_id, source_id, source_type,
--         strategy, voyage_key, similarity}, ...].
-- flags:  JSONB blob of the CLI flags the run used (top_k, strategy, source_types,
--         ef_search, reformulator, plus chunk-test-only bm25/hybrid/reranker...).

DROP TABLE IF EXISTS test_retrieval_vk_logging;
DROP TABLE IF EXISTS test_retrieval_chunk_logging;

CREATE TABLE test_retrieval_vk_logging (
    id            SERIAL       PRIMARY KEY,
    run_id        UUID         NOT NULL,
    question_id   UUID         NOT NULL REFERENCES ground_truth(question_id),
    category      TEXT         NOT NULL,
    question      TEXT         NOT NULL,
    expected_key  TEXT         NOT NULL,
    returned_keys TEXT[]       NOT NULL,
    hit           BOOLEAN      NOT NULL,
    winner_rank   INTEGER,
    vote_counts   JSONB        NOT NULL,
    chunks        JSONB        NOT NULL,
    flags         JSONB        NOT NULL,
    tested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX vk_log_run_id_idx      ON test_retrieval_vk_logging(run_id);
CREATE INDEX vk_log_question_id_idx ON test_retrieval_vk_logging(question_id);
CREATE INDEX vk_log_hit_idx         ON test_retrieval_vk_logging(hit);

CREATE TABLE test_retrieval_chunk_logging (
    id                  SERIAL       PRIMARY KEY,
    run_id              UUID         NOT NULL,
    question_id         UUID         NOT NULL REFERENCES ground_truth(question_id),
    category            TEXT         NOT NULL,
    question            TEXT         NOT NULL,
    expected_source     TEXT         NOT NULL,
    returned_source_ids TEXT[]       NOT NULL,
    hit                 BOOLEAN      NOT NULL,
    source_rank         INTEGER,
    chunks              JSONB        NOT NULL,
    flags               JSONB        NOT NULL,
    tested_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX chunk_log_run_id_idx      ON test_retrieval_chunk_logging(run_id);
CREATE INDEX chunk_log_question_id_idx ON test_retrieval_chunk_logging(question_id);
CREATE INDEX chunk_log_hit_idx         ON test_retrieval_chunk_logging(hit);
