# Step 9 — LLM Extraction

Sends Docling-generated Markdown through a local vLLM server (Nemotron-3-Nano-30B-A3B-NVFP4) and writes a structured result to Postgres.

Builds on top of `docling.markdown` (written by Step 8).

---

## What the script does

For each `sha256` in `llm_load_queue`:

1. Categorizes the document based on `char_count`:
   - `small`  ≤ 30 000 chars  (3 workers, FULL mode)
   - `medium` ≤ 95 000 chars  (2 workers, FULL mode)
   - `large`  ≤ 300 000 chars (1 worker, FULL mode)
   - `huge`   > 300 000 chars (1 worker, CLASSIFY mode with truncation to 25 000 chars)
2. Pre-flight token-budget check against `--max-model-len 131072` — documents that would exceed the ceiling are set to `skipped`.
3. Calls vLLM:
   - **FULL** → `document_restructuring.md` system prompt, `max_tokens=8196`
   - **CLASSIFY** → `document_classification.md` system prompt, `max_tokens=512`
4. Writes the result to `llm_structured` and the status to `llm_logging`.

Tiers are processed sequentially (small → medium → large → huge); within each tier the documents run in parallel via `ThreadPoolExecutor`. Workers are thread-safe — only the main thread writes to Postgres.

---

## Running the step

### 1. Start the vLLM server

```bash
docker compose -f docker/vllm/docker-compose.yml up -d
```

The first start downloads the model (~15 GB NVFP4-quantized). Caches are persisted across restarts (HF + vLLM + TorchInductor + Triton). See `docker/vllm/RUN_VLLM.md` for details.

Verify:
```bash
curl http://localhost:8002/v1/models
```

### 2. Make sure the migration has run

```bash
python3 sql_migrations/migrate.py
```

Migration `0011_llm_structured.sql` creates `llm_load_queue` (VIEW), `llm_structured` and `llm_logging`.

### 3. Pre-flight (without LLM calls)

```bash
python3 -m preprocessing.run_llm_extraction --dry-run
```

Shows the distribution per tier + GPU/RAM status without sending anything to vLLM.

### 4. Test with a few files

```bash
python3 -m preprocessing.run_llm_extraction --limit 3 --verbose
```

### 5. Full run

```bash
python3 -m preprocessing.run_llm_extraction
```

Files already marked `done` or `skipped` in `llm_logging` are filtered out. `error` rows are reprocessed automatically.

---

## CLI flags

| Flag | Default | Description |
|---|---|---|
| `--limit N` | None | Cap the number of documents (test) |
| `--voyage KEY` | None | Filter on `voyage_key` |
| `--sha256 HASH` | repeatable | Process only the listed sha256 hashes |
| `--fresh` | False | Delete `error` rows in `llm_logging` for matched sha256s before the run (force retry) |
| `--dry-run` | False | Categorize + report without LLM calls |
| `--max-tokens N` | 8196 | Output budget for FULL mode |
| `--classify-threshold N` | 300000 | Char limit where CLASSIFY takes over (-1 = always FULL) |
| `--batch-size N` | 15 | Batch size per tier (reduced dynamically under GPU/RAM pressure) |
| `--max-workers N` | None | Cap workers across all tiers |
| `--temperature F` | 0.1 | Sampling temperature |
| `--verbose` | False | Debug-level log |

`DATABASE_URL` and `LLM_BASE_URL` are read from `.env` / the environment.

---

## Output schemas

### `llm_structured` (result)

| Column | Type | Note |
|---|---|---|
| `sha256` | CHAR(64) PK | FK → `docling.sha256` |
| `mode` | TEXT | `full` / `classify` |
| `document_type` | TEXT | Parsed from the first `#` heading (FULL) or the `DOCUMENT_TYPE:` line (CLASSIFY) |
| `structured_md` | TEXT | The full LLM output (FULL) or the summary line (CLASSIFY) |
| `input_token_count` | INTEGER | vLLM `prompt_tokens` |
| `output_token_count` | INTEGER | vLLM `completion_tokens` |
| `model_name` | TEXT | Auto-detected from vLLM `/v1/models` |
| `processed_at` | TIMESTAMPTZ | — |

### `llm_logging` (per-file telemetry)

`status` ∈ {`pending`, `done`, `error`, `skipped`}; used to filter already-processed files out of `llm_load_queue`.

Also contains `started_at`, `finished_at`, `duration_ms`, `error_message`, `gpu_util_pct`, `gpu_mem_pct`, `ram_pct`, `batch_idx`, `run_id`.

---

## Verification queries

```sql
-- Status distribution
SELECT status, COUNT(*) FROM llm_logging GROUP BY status;

-- Tier distribution
SELECT size_category, mode, COUNT(*)
FROM   llm_logging
GROUP  BY size_category, mode
ORDER  BY size_category;

-- Token usage per mode
SELECT mode,
       AVG(input_token_count)::INT AS avg_in,
       AVG(output_token_count)::INT AS avg_out,
       MAX(input_token_count) AS max_in
FROM   llm_structured
GROUP  BY mode;

-- Error details
SELECT sha256, file_path, error_message
FROM   llm_logging
WHERE  status = 'error'
ORDER  BY finished_at DESC
LIMIT  20;
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `connection refused` on 8002 | vLLM not ready | `curl http://localhost:8002/v1/models`, wait and retry |
| Many `skipped` with "pre-flight: ..." | Documents exceed 131k tokens after truncation | Lower `--classify-threshold` so more documents take the CLASSIFY path |
| OOM during inference | `--gpu-memory-utilization` too high on vLLM | Lower it in `docker/vllm/docker-compose.yml` (e.g. 0.75) |
| Slow large tier | Expected — 100k+ tokens on 270 GB/s LPDDR5x takes several minutes per file | Use `--limit` when testing |
| Empty output for FULL mode | The model hit the `max_tokens=8196` cap without finishing | Check `output_token_count` — if = 8196, the document is too complex to restructure; consider running CLASSIFY instead |
