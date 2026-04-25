-- Backfill: video/* attachments were not excluded by the original classifier.
-- Mirrors the updated _EXCLUDED_PREFIXES = ("image/", "video/") in classify_attachment.py.
UPDATE attachments
SET docling_ready = FALSE
WHERE docling_ready = TRUE
  AND lower(file_type) LIKE 'video/%';
