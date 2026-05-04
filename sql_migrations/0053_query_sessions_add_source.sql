ALTER TABLE queries DROP CONSTRAINT IF EXISTS queries_session_id_fkey;

CREATE TABLE query_sessions_new (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username   TEXT NOT NULL REFERENCES users(username),
    source     TEXT CHECK (source IN ('terminal', 'test', 'application')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO query_sessions_new (session_id, username, source, created_at)
SELECT qs.session_id, qs.username, q.source, qs.created_at
FROM query_sessions qs
LEFT JOIN (
    SELECT DISTINCT ON (session_id) session_id, source
    FROM queries
    WHERE session_id IS NOT NULL
    ORDER BY session_id, created_at
) q ON q.session_id = qs.session_id;

DROP TABLE query_sessions;
ALTER TABLE query_sessions_new RENAME TO query_sessions;

ALTER TABLE queries
    ADD CONSTRAINT queries_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES query_sessions(session_id);
