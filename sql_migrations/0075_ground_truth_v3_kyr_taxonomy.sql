-- Switch ground_truth_v3 to the four-class Know Your RAG (COLING 2025) taxonomy:
-- fact_single, summary, reasoning, unanswerable.
-- Drops the previous multi_context and generic categories, adds back unanswerable.
-- Existing rows in dropped categories are deleted before tightening the check.

DELETE FROM ground_truth_v3 WHERE category IN ('multi_context', 'generic');

ALTER TABLE ground_truth_v3 DROP CONSTRAINT IF EXISTS ground_truth_v3_category_check;

ALTER TABLE ground_truth_v3
    ADD CONSTRAINT ground_truth_v3_category_check
    CHECK (category IN ('fact_single', 'summary', 'reasoning', 'unanswerable'));
