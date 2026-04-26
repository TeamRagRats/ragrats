-- Step 9 — LLM Extraction. Replace llm_load_queue so it excludes rows whose
-- docling markdown is essentially empty (only <!-- image --> placeholders,
-- HTML comments, or whitespace). Without this filter, the LLM is handed
-- ~14 chars of "<!-- image -->" and, forced by the strict output schema in
-- system_prompts/llm_extraction/document_restructuring.md, hallucinates a
-- generic shipping document (typically "Bill of Lading"). Threshold: ≥50
-- chars of real content after stripping placeholders/whitespace.
CREATE OR REPLACE VIEW llm_load_queue AS
SELECT DISTINCT ON (d.sha256)
       d.sha256,
       d.markdown,
       d.char_count,
       d.token_count,
       a.email_id,
       a.voyage_key,
       a.file_path,
       a.file_type
FROM   docling d
JOIN   attachments a ON a.sha256 = d.sha256
WHERE  d.markdown IS NOT NULL
  AND  LENGTH(REGEXP_REPLACE(d.markdown, '<!--[^>]*-->|\s+', '', 'g')) >= 50
ORDER BY d.sha256;
