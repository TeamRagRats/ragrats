-- Capture the exact input each model received, so any logged query can be
-- replayed or inspected after the fact.
--   retrieval_logging.embed_input  = the text that was embedded for the query
--     (original or reformulated, depending on --reformulate).
--   generation_logging.llm_input   = the full user prompt sent to the LLM
--     (CONTEXT + QUESTION assembly).

ALTER TABLE retrieval_logging  ADD COLUMN IF NOT EXISTS embed_input TEXT;
ALTER TABLE generation_logging ADD COLUMN IF NOT EXISTS llm_input  TEXT;
