-- Revert table rename (0078 was a mistake) and rename strategies → strategy.
ALTER TABLE test_retrieval_logging RENAME TO retrieval_logging;
ALTER TABLE retrieval_logging RENAME COLUMN strategies TO strategy;
