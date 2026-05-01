-- Add strategy column to chunks so multiple chunking strategies can coexist
-- for the same source document (e.g. naive vs late chunking of the same email).

-- 1. Add strategy column with a sensible default for existing rows
ALTER TABLE chunks ADD COLUMN strategy text NOT NULL DEFAULT 'paragraph';

-- 2. Drop the old unique constraint that didn't include strategy
ALTER TABLE chunks DROP CONSTRAINT chunks_source_type_source_id_chunk_index_key;

-- 3. New unique constraint includes strategy
ALTER TABLE chunks ADD CONSTRAINT chunks_source_type_source_id_strategy_chunk_index_key
    UNIQUE (source_type, source_id, strategy, chunk_index);

-- 4. Expand source_type to include thread and phase
ALTER TABLE chunks DROP CONSTRAINT chunks_source_type_check;
ALTER TABLE chunks ADD CONSTRAINT chunks_source_type_check
    CHECK (source_type = ANY (ARRAY['email', 'voyage', 'thread', 'phase']));

-- 5. Expand strategy check
ALTER TABLE chunks ADD CONSTRAINT chunks_strategy_check
    CHECK (strategy = ANY (ARRAY['paragraph', 'late', 'late_overlap']));
