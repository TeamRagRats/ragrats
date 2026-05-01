ALTER TABLE ground_truth
ADD COLUMN IF NOT EXISTS source_chunk_id UUID REFERENCES chunks(chunk_id);
