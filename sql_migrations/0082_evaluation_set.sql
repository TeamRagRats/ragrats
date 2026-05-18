-- Curated QA dataset for evaluation.
-- Holds queries reviewed as correct ('original') and will later grow with
-- generated questions ('synthetic'). query_id is nullable so synthetic rows
-- can live alongside originals without a backing logged query.

CREATE TABLE evaluation_set (
    evaluation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_origin TEXT NOT NULL CHECK (question_origin IN ('original', 'synthetic')),
    query_id        UUID UNIQUE REFERENCES queries(query_id),
    input           TEXT NOT NULL,
    output          TEXT NOT NULL,
    chunks          JSONB,
    chunks_expanded JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO evaluation_set (question_origin, query_id, input, output, chunks, chunks_expanded)
SELECT DISTINCT ON (r.query_id)
    'original',
    r.query_id,
    r.query_text,
    r.answer,
    rl.chunks,
    rl.chunks_expanded
FROM reviews r
JOIN retrieval_logging rl ON rl.query_id = r.query_id
WHERE r.is_correct = TRUE
ORDER BY r.query_id, r.created_at DESC;
