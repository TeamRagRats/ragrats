CREATE OR REPLACE VIEW docling_load_queue AS
SELECT DISTINCT ON (sha256) sha256, email_id, voyage_key, file_path, file_type
FROM attachments
WHERE sha256 IS NOT NULL
ORDER BY sha256;
