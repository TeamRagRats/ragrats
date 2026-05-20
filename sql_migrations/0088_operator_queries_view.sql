-- Operator queries view: real queries we treat as style references for
-- ground-truth generation. Excludes internal/dev/synthetic usernames
-- (case-insensitive) so we only see queries posed by real operators.

CREATE OR REPLACE VIEW operator_queries_v AS
SELECT
    query_id,
    query_text,
    username,
    source,
    session_id,
    created_at
FROM queries
WHERE LOWER(username) NOT IN ('nsl', 'dev', 'developer');
