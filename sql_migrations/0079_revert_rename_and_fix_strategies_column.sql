-- Rename strategies column → strategy on retrieval_logging.
ALTER TABLE retrieval_logging RENAME COLUMN strategies TO strategy;
