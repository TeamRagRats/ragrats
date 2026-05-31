# Run the docling pipeline

## Prerequisites

1. **Postgres is up** — see `docker/postgres/START_DATABASE.md`:
   ```bash
   docker compose -f docker/postgres/docker-compose.yml up -d
   ```

2. **The schema is created** from `sql/db.sql`:
   ```bash
   python sql/init_db.py
   ```

3. **Attachments are imported** (steps 01–06 via `run_ingest.py`), so the `docling_load_queue` view has rows.

4. **The docling image is built**:
   ```bash
   docker compose -f docker/docling/docker-compose.yml build
   ```

## Run the pipeline

**Everyday run** (recommended) — the wrapper script hardcodes `--resume` so files marked `status='done'` are skipped:
```bash
./src/preprocessing/step_08_docling/run_docling.sh
```

**Direct invocation** without the wrapper:
```bash
docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.run_docling --resume
```

`DATABASE_URL` overrides the `.env` value so the container reaches the postgres container on its internal network name (not host localhost).

## CLI flags

| Flag | Use | When |
|---|---|---|
| `--limit N` | Process only N files | Smoke test, debugging |
| `--voyage <key>` | Filter on `voyage_key` | Test one voyage, re-run after a new import |
| `--batch-size N` | Override the default (15) | Tune on OOM or a slow GPU |
| `--resume` | Skip files with `status='done'` in `docling_logging` | Standard on re-runs (set by the wrapper script) |
| `--sha256 HASH` (repeatable) | Re-process specific files | Testing individual documents; forces `resume=False` |
| `--verbose` | DEBUG logging | Troubleshooting |

## Typical runs

**Smoke test — 5 files:**
```bash
./src/preprocessing/step_08_docling/run_docling.sh --limit 5 --verbose
```

**One voyage:**
```bash
./src/preprocessing/step_08_docling/run_docling.sh --voyage CAPTAIN_RAVI_1
```

**Re-process specific files (sha256 filter):**
```bash
./src/preprocessing/step_08_docling/run_docling.sh \
  --sha256 abc123... --sha256 def456...
```

**Re-process everything from scratch (overwrites existing rows):**
```bash
# Omit --resume by invoking the module directly
docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.run_docling --verbose
```

## Configuration

The pipeline runs Docling with the following explicitly chosen high-quality options (`docling_runner.py:build_docling_converter`):

- **Layout:** Heron (`ds4sd/docling-layout-heron`) when the installed Docling version exposes it; otherwise falls back to the default with a warning.
- **Table:** TableFormerMode.ACCURATE + `do_cell_matching=True`.
- **Picture description:** IBM Granite Vision 3.3-2b generates image descriptions and embeds them in the markdown next to the `<!-- image -->` placeholders.
- **GPU:** AcceleratorDevice.AUTO (CUDA on machines with an NVIDIA driver).

## Check the result

```sql
-- How many files have been processed?
SELECT status, count(*) FROM docling_logging GROUP BY status;

-- Most recent runs
SELECT sha256, duration_ms, char_count, status, error_message
FROM docling_logging ORDER BY finished_at DESC NULLS LAST LIMIT 10;

-- Confirm markdown is stored
SELECT count(*) AS rows_with_md FROM docling WHERE markdown IS NOT NULL;
```

## Troubleshooting

- **`connection refused` against postgres** → the postgres container is not up, or the `postgres_default` network does not exist. Start postgres first.
- **`Input missing: /input/…`** → `data/attachment/` is empty or the mount is wrong. Check `docker-compose.yml`.
- **GPU not detected** → the container could not reserve the NVIDIA runtime. Run `docker run --rm --gpus all nvidia/cuda:13.0.0-base-ubuntu22.04 nvidia-smi` to verify the host setup.
- **`nvrtc: invalid --gpu-architecture`** → the GPU architecture is too new for the torch wheel. Requires a rebuild with a newer torch (see Dockerfile).
- **VLM custom code error (`trust_remote_code=True`)** → a model was switched to one that requires custom code. Change `repo_id` in `docling_runner.py` to a model compatible with the standard loader (Granite Vision is tested).
