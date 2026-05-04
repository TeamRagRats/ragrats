ALTER TABLE generation_logging ADD COLUMN _new_qid UUID;

UPDATE generation_logging gl
SET _new_qid = gl.query_id
FROM (
    SELECT DISTINCT ON (query_id) generation_id
    FROM generation_logging
    ORDER BY query_id, created_at
) first_row
WHERE gl.generation_id = first_row.generation_id;

UPDATE generation_logging
SET _new_qid = gen_random_uuid()
WHERE _new_qid IS NULL;

INSERT INTO queries (query_id, query_text, source, username)
SELECT gl._new_qid, q.query_text, q.source, q.username
FROM generation_logging gl
JOIN queries q ON q.query_id = gl.query_id
WHERE gl._new_qid != gl.query_id;

UPDATE generation_logging
SET query_id = _new_qid
WHERE query_id != _new_qid;

ALTER TABLE generation_logging DROP COLUMN _new_qid;

CREATE TABLE generation_logging_new (
    query_id            UUID PRIMARY KEY REFERENCES queries(query_id),
    query_text          TEXT NOT NULL,
    answer              TEXT NOT NULL,
    system_prompt       TEXT NOT NULL,
    model               TEXT NOT NULL,
    temperature         REAL NOT NULL,
    max_tokens          INTEGER NOT NULL,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    generation_ms       INTEGER,
    total_ms            INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO generation_logging_new
SELECT
    gl.query_id,
    q.query_text,
    gl.answer,
    gl.system_prompt,
    gl.model,
    gl.temperature,
    gl.max_tokens,
    gl.prompt_tokens,
    gl.completion_tokens,
    gl.generation_ms,
    gl.total_ms,
    gl.created_at
FROM generation_logging gl
JOIN queries q ON gl.query_id = q.query_id;

DROP TABLE generation_logging;

ALTER TABLE generation_logging_new RENAME TO generation_logging;
