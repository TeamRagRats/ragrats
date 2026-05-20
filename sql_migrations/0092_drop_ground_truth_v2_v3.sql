-- Drop the superseded ground_truth iterations. The canonical table is the
-- unversioned `ground_truth` (migration 0089). v2 was empty; v3's 368 rows are
-- retired alongside the generation test, which will be repointed to ground_truth.
-- No foreign keys reference either table.

DROP TABLE IF EXISTS ground_truth_v2;
DROP TABLE IF EXISTS ground_truth_v3;
