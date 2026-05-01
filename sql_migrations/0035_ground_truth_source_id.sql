-- Rename source_email_id → source_id (TEXT) to match chunks.source_id convention.
-- Drops the UUID FK constraint since source_id can be an email UUID or a voyage_key.
ALTER TABLE ground_truth
    DROP COLUMN source_email_id,
    ADD COLUMN source_id TEXT;
