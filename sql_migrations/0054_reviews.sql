CREATE TABLE IF NOT EXISTS reviews (
    review_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id   UUID NOT NULL REFERENCES queries(query_id),
    username   TEXT NOT NULL REFERENCES users(username),
    is_correct BOOLEAN NOT NULL,
    feedback   TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
