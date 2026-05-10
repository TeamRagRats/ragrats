-- Add text column to ground_truth_v3 to store the chunk the question was generated from.

ALTER TABLE ground_truth_v3
    ADD COLUMN IF NOT EXISTS text TEXT;
