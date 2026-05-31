# Test: step_03_generation

Tests generation quality with realistic context from the retrieval system.

Joins `ground_truth` with `test_retrieval_chunk_logging` and takes only questions where `hit=true` (the correct chunks were returned). Groups by K value and evaluates generation for each K separately. Scores each answer with cosine similarity + LLM-as-judge (1–5). Reports per K and per category: `fact_single`, `summary`, `reasoning`.

```bash
# Requires that the chunk-retrieval test has been run first
python run_test.py --retrieval-run-id <UUID>
```

**Flags:**
- `--retrieval-run-id` (required) — UUID from a run in `test_retrieval_chunk_logging`; ensures generation is only evaluated on one strategy/configuration at a time
- `--embed-url` — embed server base URL (default: `http://localhost:8003/v1`)
- `--llm-url` — LLM server base URL (default: `http://localhost:8002/v1`)
- `--temperature` — generation temperature (default: `0.3`)
- `--max-tokens` — max tokens in the answer (default: `2500`)
