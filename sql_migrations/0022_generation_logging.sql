CREATE TABLE IF NOT EXISTS generation_logging (
    generation_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    retrieval_run_id  UUID REFERENCES retrieval_logging(run_id),
    query             TEXT NOT NULL,
    answer            TEXT NOT NULL,
    system_prompt     TEXT NOT NULL,
    model             TEXT NOT NULL,
    temperature       REAL NOT NULL,
    max_tokens        INTEGER NOT NULL,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    generation_ms     INTEGER,
    total_ms          INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
