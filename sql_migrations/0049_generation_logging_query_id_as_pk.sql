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
