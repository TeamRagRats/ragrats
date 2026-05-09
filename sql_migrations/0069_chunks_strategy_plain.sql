-- Allow strategy='plain' for per-email chunks where the embedding input is
-- just body_cleaned (no thread summary, no enrichment). Baseline control for
-- comparing against 'late' and 'context'.

ALTER TABLE chunks DROP CONSTRAINT chunks_strategy_check;
ALTER TABLE chunks ADD CONSTRAINT chunks_strategy_check
    CHECK (strategy = ANY (ARRAY['late', 'context', 'plain']));
