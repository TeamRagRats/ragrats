-- Tighten ground_truth: body_cleaned and structured_md are always present
-- (structured_md is "" when the email has no attachments, never NULL).

UPDATE ground_truth SET body_cleaned  = '' WHERE body_cleaned  IS NULL;
UPDATE ground_truth SET structured_md = '' WHERE structured_md IS NULL;

ALTER TABLE ground_truth ALTER COLUMN body_cleaned  SET NOT NULL;
ALTER TABLE ground_truth ALTER COLUMN structured_md SET NOT NULL;
