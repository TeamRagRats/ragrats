-- Backfill: archives (rar, 7z, tar, gz, bz2) were slipping through the
-- docling_ready filter in 0005, which only excluded zip variants. Mirrors
-- the extended _EXCLUDED_TYPES set in classify_attachment.py so existing
-- attachments rows match the new classifier behaviour.
UPDATE attachments
SET docling_ready = FALSE
WHERE docling_ready = TRUE
  AND lower(file_type) IN (
      'application/zip',
      'application/x-zip-compressed',
      'application/x-zip',
      'application/x-rar-compressed',
      'application/vnd.rar',
      'application/x-rar',
      'application/x-7z-compressed',
      'application/x-tar',
      'application/gzip',
      'application/x-gzip',
      'application/x-bzip2'
  );
