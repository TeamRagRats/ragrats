-- Revert 0090: allow body_cleaned and structured_md to be NULL again.

ALTER TABLE ground_truth ALTER COLUMN body_cleaned  DROP NOT NULL;
ALTER TABLE ground_truth ALTER COLUMN structured_md DROP NOT NULL;
