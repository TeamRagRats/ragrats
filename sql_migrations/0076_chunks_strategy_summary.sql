-- Allow strategy='summary' for chunks whose stored text IS the LLM-generated
-- summary itself (email_summary, attachment_summary). The summary pipeline
-- already writes strategy='summary' — this migration just opens the CHECK.

ALTER TABLE chunks DROP CONSTRAINT chunks_strategy_check;
ALTER TABLE chunks ADD CONSTRAINT chunks_strategy_check
    CHECK (strategy = ANY (ARRAY['late', 'context', 'plain', 'summary']));
