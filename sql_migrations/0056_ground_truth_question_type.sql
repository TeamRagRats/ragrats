ALTER TABLE ground_truth
    ADD COLUMN question_type TEXT NOT NULL DEFAULT 'extractive'
        CHECK (question_type IN ('extractive', 'investigative'));

-- Investigative questions have no single source chunk
ALTER TABLE ground_truth
    ALTER COLUMN source_chunk_id DROP NOT NULL;
