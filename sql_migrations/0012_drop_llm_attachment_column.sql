-- Drop the legacy llm_attachment column. LLM-extracted attachment text is now
-- stored in llm_structured.structured_md (see 0011_llm_structured.sql), and
-- step_07_summaries reads from there instead.
ALTER TABLE docling DROP COLUMN IF EXISTS llm_attachment;
