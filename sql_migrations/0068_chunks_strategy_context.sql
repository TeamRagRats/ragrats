-- Allow strategy='context' for per-email chunks where the embedding input is
-- (prior-thread summary + email body), but the stored text is just the body.

ALTER TABLE chunks DROP CONSTRAINT chunks_strategy_check;
ALTER TABLE chunks ADD CONSTRAINT chunks_strategy_check
    CHECK (strategy = ANY (ARRAY['late', 'context']));
