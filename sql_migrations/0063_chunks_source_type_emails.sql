-- Add 'emails' to chunks.source_type for late-embedded email bodies (step_06_embedding/email_late).
ALTER TABLE chunks DROP CONSTRAINT chunks_source_type_check;

ALTER TABLE chunks ADD CONSTRAINT chunks_source_type_check
    CHECK (source_type = ANY (ARRAY[
        'email_summaries'::text,
        'fixture_summaries'::text,
        'phase'::text,
        'llm_structured'::text,
        'emails'::text
    ]));
