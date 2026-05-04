-- Add nullable FK column
ALTER TABLE generation_logging ADD COLUMN query_id UUID REFERENCES queries(query_id);

-- Backfill via retrieval_logging (generation_logging.retrieval_run_id → retrieval_logging.run_id → queries)
UPDATE generation_logging gl
SET query_id = rl.query_id
FROM retrieval_logging rl
WHERE gl.retrieval_run_id = rl.run_id;

-- Handle orphaned rows (no retrieval_run_id or mismatch) — backfill from own query text
WITH dev_user AS (
    SELECT user_id FROM users WHERE username = 'developer'
),
inserted AS (
    INSERT INTO queries (query_text, source, user_id)
    SELECT DISTINCT gl.query, 'terminal', dev_user.user_id
    FROM generation_logging gl, dev_user
    WHERE gl.query_id IS NULL AND gl.query IS NOT NULL
    RETURNING query_id, query_text
)
UPDATE generation_logging gl
SET query_id = inserted.query_id
FROM inserted
WHERE gl.query = inserted.query_text AND gl.query_id IS NULL;

-- Make NOT NULL
ALTER TABLE generation_logging ALTER COLUMN query_id SET NOT NULL;

-- Drop old column
ALTER TABLE generation_logging DROP COLUMN query;
