-- Wipe all test data and ground truth to start fresh with cleaner ground truth generation.
TRUNCATE TABLE test_generation_accuracy_logging;
TRUNCATE TABLE test_chunk_retrieval_logging;
TRUNCATE TABLE test_voyage_key_logging;
TRUNCATE TABLE test_logging;
TRUNCATE TABLE ground_truth;
