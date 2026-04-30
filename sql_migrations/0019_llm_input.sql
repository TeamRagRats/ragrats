ALTER TABLE email_attach_summaries ADD COLUMN IF NOT EXISTS llm_input TEXT;
ALTER TABLE fixture_summaries       ADD COLUMN IF NOT EXISTS llm_input TEXT;
ALTER TABLE phase_summaries         ADD COLUMN IF NOT EXISTS llm_input TEXT;
ALTER TABLE voyage_summaries        ADD COLUMN IF NOT EXISTS llm_input TEXT;
ALTER TABLE thread_summaries        ADD COLUMN IF NOT EXISTS llm_input TEXT;
