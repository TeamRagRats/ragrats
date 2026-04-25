-- Backfill: archives often arrive with a generic application/octet-stream
-- MIME type, so MIME-only filtering misses them. Mirrors the new
-- _EXCLUDED_EXTENSIONS check in classify_attachment.py — if the filename
-- ends in a known archive extension, the attachment is not docling-ready
-- regardless of MIME.
UPDATE attachments
SET docling_ready = FALSE
WHERE docling_ready = TRUE
  AND lower(file_name) ~ '\.(zip|rar|7z|tar|gz|tgz|bz2|tbz2|xz|lz|lzma)$';
