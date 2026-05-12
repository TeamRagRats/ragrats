-- Track which chunk strategy each ground_truth_v3 question was generated from.
-- Allows the same source chunk to produce different questions per strategy
-- (plain / late / context / summary).

ALTER TABLE ground_truth_v3
    ADD COLUMN IF NOT EXISTS strategy TEXT NOT NULL DEFAULT 'plain'
    CHECK (strategy IN ('plain', 'late', 'context', 'summary'));

ALTER TABLE ground_truth_v3 ALTER COLUMN strategy DROP DEFAULT;

CREATE INDEX IF NOT EXISTS gt_v3_strategy_idx ON ground_truth_v3 (strategy);
