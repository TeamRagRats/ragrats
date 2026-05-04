CREATE TABLE queries_new (
    query_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_text TEXT NOT NULL,
    username   TEXT NOT NULL,
    source     TEXT NOT NULL CHECK (source IN ('terminal', 'test')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO queries_new (query_id, query_text, username, source, created_at)
SELECT query_id, query_text, username, source, created_at
FROM queries;

ALTER TABLE retrieval_logging DROP CONSTRAINT IF EXISTS retrieval_logging_query_id_fkey;
ALTER TABLE generation_logging DROP CONSTRAINT IF EXISTS generation_logging_query_id_fkey;

DROP TABLE queries;

ALTER TABLE queries_new RENAME TO queries;

ALTER TABLE retrieval_logging
    ADD CONSTRAINT retrieval_logging_query_id_fkey
    FOREIGN KEY (query_id) REFERENCES queries(query_id);

ALTER TABLE generation_logging
    ADD CONSTRAINT generation_logging_query_id_fkey
    FOREIGN KEY (query_id) REFERENCES queries(query_id);
