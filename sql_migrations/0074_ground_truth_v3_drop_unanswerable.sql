-- Remove unanswerable from ground_truth_v3 category constraint.
-- Delete any existing unanswerable rows before tightening the check.

DELETE FROM ground_truth_v3 WHERE category = 'unanswerable';

ALTER TABLE ground_truth_v3 DROP CONSTRAINT IF EXISTS ground_truth_v3_category_check;

ALTER TABLE ground_truth_v3
    ADD CONSTRAINT ground_truth_v3_category_check
    CHECK (category IN ('fact_single', 'summary', 'multi_context', 'reasoning', 'generic'));
