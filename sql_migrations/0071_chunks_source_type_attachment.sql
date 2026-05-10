-- Allow source_type='attachment' for late/context chunks produced from llm_structured docs.

ALTER TABLE chunks DROP CONSTRAINT chunks_source_type_check;

ALTER TABLE chunks ADD CONSTRAINT chunks_source_type_check
    CHECK (source_type = ANY (ARRAY[
        'email_summaries'::text,
        'fixture_summaries'::text,
        'phase'::text,
        'llm_structured'::text,
        'email'::text,
        'attachment'::text
    ]));
