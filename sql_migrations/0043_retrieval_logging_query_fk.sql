-- Add nullable FK column
ALTER TABLE retrieval_logging ADD COLUMN query_id UUID REFERENCES queries(query_id);

-- Backfill: create query rows from existing query text, then link
WITH dev_user AS (
    SELECT user_id FROM users WHERE username = 'developer'
),
inserted AS (
    INSERT INTO queries (query_text, source, user_id)
    SELECT DISTINCT rl.query, 'terminal', dev_user.user_id
    FROM retrieval_logging rl, dev_user
    WHERE rl.query IS NOT NULL
    RETURNING query_id, query_text
)
UPDATE retrieval_logging rl
SET query_id = inserted.query_id
FROM inserted
WHERE rl.query = inserted.query_text;

-- Make NOT NULL (safe now that all rows are linked)
ALTER TABLE retrieval_logging ALTER COLUMN query_id SET NOT NULL;

-- Drop old column
ALTER TABLE retrieval_logging DROP COLUMN query;
