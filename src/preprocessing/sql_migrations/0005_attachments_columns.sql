ALTER TABLE attachments
    ADD COLUMN IF NOT EXISTS file_name     TEXT,
    ADD COLUMN IF NOT EXISTS size_bytes    BIGINT,
    ADD COLUMN IF NOT EXISTS docling_ready BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill: mirrors is_docling_ready() in classify_attachment.py —
-- excludes image/* and zip MIME types; everything else is marked ready.
UPDATE attachments
SET docling_ready = (
    file_type IS NULL
    OR (
        lower(file_type) NOT LIKE 'image/%'
        AND lower(file_type) NOT IN (
            'application/zip',
            'application/x-zip-compressed',
            'application/x-zip'
        )
    )
)
WHERE docling_ready = FALSE;

CREATE OR REPLACE VIEW docling_load_queue AS
SELECT DISTINCT ON (sha256) sha256, email_id, voyage_key, file_path, file_type
FROM attachments
WHERE sha256 IS NOT NULL
  AND docling_ready = TRUE
ORDER BY sha256;
