ALTER TABLE queries ADD COLUMN username TEXT;

UPDATE queries q
SET username = u.username
FROM users u
WHERE q.user_id = u.user_id;

ALTER TABLE queries ALTER COLUMN username SET NOT NULL;

ALTER TABLE queries DROP COLUMN user_id;
