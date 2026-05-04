CREATE TABLE IF NOT EXISTS queries (
    query_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_text TEXT NOT NULL,
    source     TEXT NOT NULL CHECK (source IN ('terminal', 'test')),
    user_id    UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
