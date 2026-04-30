-- Only process attachments smaller than 5 MB through the docling pipeline.
-- Files where size_bytes is NULL (pre-migration rows) are included so nothing
-- already queued is silently dropped.
CREATE OR REPLACE VIEW docling_load_queue AS
SELECT DISTINCT ON (sha256) sha256, email_id, voyage_key, file_path, file_type
FROM attachments
WHERE sha256 IS NOT NULL
  AND docling_ready = TRUE
  AND (size_bytes IS NULL OR size_bytes < 5242880)
ORDER BY sha256;
