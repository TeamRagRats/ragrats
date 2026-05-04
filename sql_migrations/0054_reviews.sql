CREATE TABLE IF NOT EXISTS reviews (
    query_id   UUID PRIMARY KEY REFERENCES queries(query_id),
    query_text TEXT NOT NULL,
    answer     TEXT NOT NULL,
    username   TEXT NOT NULL REFERENCES users(username),
    is_correct BOOLEAN NOT NULL,
    feedback   TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
