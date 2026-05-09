-- Update chunks.source_type CHECK constraint:
--   drop 'thread_summaries' and 'voyage'
--   add 'llm_structured'
-- Allowed set: email_summaries, fixture_summaries, phase, llm_structured

ALTER TABLE chunks DROP CONSTRAINT chunks_source_type_check;

ALTER TABLE chunks ADD CONSTRAINT chunks_source_type_check
    CHECK (source_type = ANY (ARRAY[
        'email_summaries'::text,
        'fixture_summaries'::text,
        'phase'::text,
        'llm_structured'::text
    ]));
