-- Persist the LLM-reformulated query alongside each ground-truth question.
-- Populated once by step_00_query_reformulation/populate_ground_truth.py so the
-- retrieval sweeps read it from the DB instead of re-running reformulation (and
-- losing that work on a crash). Nullable: rows stay untouched until populated.

ALTER TABLE ground_truth ADD COLUMN IF NOT EXISTS question_reformulated TEXT;
