-- Drop the docling_document JSONB column. Verified that the new pipeline
-- only persists markdown and writes NULL into this column, and that no
-- downstream consumer reads it. Embedded image payloads were the original
-- reason this column kept blowing past Postgres' 256 MB per-jsonb-value
-- limit, so removing it also reclaims the space taken by historical rows.
ALTER TABLE docling DROP COLUMN IF EXISTS docling_document;
