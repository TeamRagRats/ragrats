CREATE TABLE IF NOT EXISTS query_sessions (
    session_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username     TEXT NOT NULL REFERENCES users(username),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS session_messages (
    message_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID NOT NULL REFERENCES query_sessions(session_id),
    role         TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content      TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
