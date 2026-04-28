# Step 8 — LLM Extraction (udkast)

Overførsel af gammel Step 5 (`llm_to_db.py`) til ny Postgres-baseret kodebase
på DGX Spark (GB10 chip, 128 GB unified memory).

---

## Placering: `step_08_llm_extraction/`

Step 7 er Docling. Det nye step bliver **Step 8 — LLM Extraction**, og bygger
oven på `docling.markdown` (PostgreSQL).

```
src/preprocessing/
├── run_llm_extraction.py              ← entry point (analog til run_docling.py)
└── step_08_llm_extraction/
    ├── __init__.py
    ├── constants.py                   ← size-tærskler, worker-counts, batch-size
    ├── prompts.py                     ← loader de to system prompts
    ├── db.py                          ← pending query + insert til llm_structured/llm_logging
    └── extractor.py                   ← process_single_document(task, llm)
```

JSON-checkpoint droppes — `llm_logging.status` er sandheden (mirrors docling-mønsteret).

---

## Database — mirror af docling-mønsteret

Tre objekter, præcis parallelt med `docling_load_queue` / `docling` / `docling_logging`:

```
llm_load_queue   (VIEW)      ← genererer pending-listen fra docling + attachments
llm_structured   (TABLE)     ← det strukturerede output (ren resultat-tabel)
llm_logging      (TABLE)     ← per-fil status/timing/ressource-snapshot
```

Ny migration: `0011_llm_structured.sql`.

### `llm_load_queue` (VIEW)

Henter alt fra `docling` der har markdown, beriget med attachment-info så vi kan
filtrere på `voyage_key` og diagnosticere fra filnavn:

```sql
CREATE OR REPLACE VIEW llm_load_queue AS
SELECT DISTINCT ON (d.sha256)
       d.sha256,
       d.markdown,
       d.char_count,
       d.token_count,
       a.email_id,
       a.voyage_key,
       a.file_path,
       a.file_type
FROM   docling d
JOIN   attachments a ON a.sha256 = d.sha256
WHERE  d.markdown IS NOT NULL
  AND  TRIM(d.markdown) <> ''
ORDER BY d.sha256;
```

### `llm_structured` (resultat-tabel)

```sql
CREATE TABLE IF NOT EXISTS llm_structured (
    sha256             CHAR(64) PRIMARY KEY REFERENCES docling(sha256) ON DELETE CASCADE,
    mode               TEXT NOT NULL CHECK (mode IN ('full','classify')),
    document_type      TEXT,
    structured_md      TEXT,
    input_token_count  INTEGER NOT NULL DEFAULT 0,
    output_token_count INTEGER NOT NULL DEFAULT 0,
    model_name         TEXT NOT NULL,
    processed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `llm_logging` (operationel telemetri)

```sql
CREATE TABLE IF NOT EXISTS llm_logging (
    sha256          CHAR(64) PRIMARY KEY,
    file_path       TEXT,
    file_type       TEXT,
    char_count      INTEGER,
    size_category   TEXT,
    mode            TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     BIGINT,
    status          TEXT NOT NULL CHECK (status IN ('pending','done','error','skipped')),
    error_message   TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    gpu_util_pct    INTEGER,
    gpu_mem_pct     NUMERIC(5,2),
    ram_pct         NUMERIC(5,2),
    batch_idx       INTEGER,
    run_id          UUID REFERENCES import_runs(run_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS llm_logging_status_idx ON llm_logging(status);
CREATE INDEX IF NOT EXISTS llm_logging_run_idx    ON llm_logging(run_id);
```

### Pending-fetch

```sql
SELECT q.sha256, q.markdown, q.char_count, q.voyage_key, q.file_path
FROM   llm_load_queue q
LEFT JOIN llm_logging l ON l.sha256 = q.sha256
WHERE  l.status IS NULL OR l.status = 'error';
```

`done`/`skipped` filtreres væk; `error`-rækker reprocesseres automatisk.

---

## Hardware-realiteter (DGX Spark / GB10)

- **Unified memory:** 128 GB LPDDR5x @ ~270 GB/s (deles mellem Grace CPU + Blackwell GPU).
- Hukommelse er rigelig — **memory bandwidth er flaskehalsen**, ikke VRAM-kapacitet.
- Høj concurrency giver diminishing returns på dette setup → tiered workers er essentielt.
- Lange konteksts er hukommelses-billige men *langsomme* — large-jobs vil tage minutter pr. dokument.

---

## Token-budget (med fast `max_tokens = 8 196`)

Fast overhead pr. request:
- System prompt + chat-template + margin: ~300 tokens
- Output budget: 8 196 tokens
- **= ~8 500 tokens fast pr. request**

Char→token-ratio: ~4 chars/token for shipping-dokumenter (engelsk, struktureret).

---

## Tiered workers + char-tærskler

| Tier | Workers | Char-range | Input tokens (worst) | `max_model_len` behov | Mode |
|---|---|---|---|---|---|
| **small**  | 3 | 0 – 30 000        | ~7 500   | 16 384                | FULL     |
| **medium** | 2 | 30 000 – 95 000   | ~23 750  | 32 768                | FULL     |
| **large**  | 1 | 95 000 – 300 000  | ~75 000  | **131 072 (128 k)**   | FULL     |
| **huge**   | 1 | > 300 000         | ~6 250 (truncate til 25 000 chars) | 8 192 (kører på 128 k) | CLASSIFY |

Kategorier processeres **sekventielt** (small → medium → large → huge); inden
for hver kategori parallel via `ThreadPoolExecutor`.

### vLLM-konfiguration

Én server dækker alle tiers — vLLM pre-reserverer kun KV pr. aktiv request,
så et 7k-tokens kald på en 128k-server bruger stadig kun 7k tokens KV.

Opdater `docker/vllm/docker-compose.yml`:

```yaml
--model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4
--max-model-len 131072        # var 8192
--gpu-memory-utilization 0.85 # GB10 unified memory tåler højere udnyttelse
--dtype auto
--trust-remote-code
--port 8000
```

### VRAM-profil under last (groft)

KV-cache for Nemotron-30B-A3B (MoE, ~3B aktive) i fp16 KV: ~150-200 KB/token.

| Tier | Concurrent KV worst-case | Bemærkning |
|---|---|---|
| small (3 × 16k) | ~9 GB | trivielt |
| medium (2 × 32k) | ~12 GB | OK |
| large (1 × 85k) | ~17 GB | komfortabelt med 128 GB unified |
| huge (1 × 8k) | ~1.5 GB | trivielt |

---

## Hvad der genbruges 1:1 (intet duplikat)

| Komponent gammel plan | Allerede i repoet | Kommentar |
|---|---|---|
| `LLMClient` + `chat_with_usage` | `step_07_summaries/llm_client.py` | Identisk interface — bare importer |
| `wait_for_server` | samme fil | — |
| `_FallbackClient` | **droppes** | Vi har den rigtige klient |
| GPU/RAM-monitorering, `cleanup_memory` | `step_08_docling/resources.py` | Importeres direkte |
| Run-/step-tracking | `shared/logging/run_logger.py` | Bruges som i `run_summaries.py` |
| System prompts | `system_prompts/llm_extraction/` | Allerede flyttet ind |
| Container management (`ensure_vllm_running`) | **droppes** | vLLM kører via `docker/vllm/docker-compose.yml` — vent bare med `wait_for_server` |

---

## Bevaret kernelogik

1. **To-prompt strategi** — FULL (8 196 output) for small/medium/large; CLASSIFY (8 196 cap, men outputtet er reelt ~50 tok) for huge med truncation til 25 000 chars.
2. **Tiered workers** — 3/2/1/1 som ovenfor; sekventielle kategorier.
3. **DB-write invariant** — workers læser kun `LLMClient` (HTTP), main thread skriver til Postgres. Samme regel som `email_summaries.py` allerede følger her.
4. **Dynamisk batch-resize** — 80%/90% GPU/RAM tærskler, batch reduceres aldrig op. Logikken i `run_docling.py:_adjust_batch_size` kan kopieres direkte.
5. **Pre-flight token-check** — før hvert kald, beregn `tokenizer(prompt) + max_tokens + safety` og smid CLASSIFY-fallback eller `skipped`-status hvis det overstiger 131 072. Hård crash-prevention mod tokenizer-variance.

---

## CLI (i `run_llm_extraction.py`)

| Flag | Default | Note |
|---|---|---|
| `--limit N` | None | Cap antal dokumenter (test) |
| `--voyage KEY` | None | Filter pr. voyage_key |
| `--sha256 HASH` | repeatable | Process specifikke filer (matcher `run_docling.py`) |
| `--fresh` | False | Slet `error`-rækker i `llm_logging` for matchede sha256 før kørsel |
| `--dry-run` | False | Scan + kategoriser uden LLM-kald |
| `--max-tokens` | 8196 | Output-budget (FULL mode) |
| `--classify-threshold` | 300000 | Char-grænse for CLASSIFY (-1 = altid FULL) |
| `--skip-threshold` | None | Char-grænse over hvilken sha256 sættes til `skipped` |
| `--batch-size` | 15 | Batch-størrelse inden for hver kategori |
| `--temperature` | 0.1 | Sampling temperature |
| `--verbose` | False | Debug-log |

Ingen `--db` (`DATABASE_URL` fra `.env`); ingen `--demo` (`--limit 5 --verbose` dækker).

---

## Eksekverings-flow

```
run_llm_extraction.main():
  wait_for_server(LLM_BASE_URL)              # som run_summaries.py
  llm = LLMClient()
  with connect() as conn:
    run_id = start_run(conn)
    pending = db.fetch_pending(conn, voyage, sha256_filter, limit)
    by_tier = categorize(pending)            # {small: [...], medium: [...], large: [...], huge: [...]}

    for tier in ('small', 'medium', 'large', 'huge'):
      workers = WORKERS_BY_TIER[tier]        # 3 / 2 / 1 / 1
      with step(conn, run_id, f"llm_extraction_{tier}"):
        process_tier(conn, llm, by_tier[tier], workers, run_id)

    finish_run(conn, run_id, status)


process_tier(tasks, workers):
  for batch in chunks(tasks, batch_size):
    db.log_batch_pending(conn, batch, run_id, batch_idx)
    with ThreadPoolExecutor(max_workers=workers) as ex:
      futures = {ex.submit(extractor.process, t, llm): t for t in batch}
      results = [f.result() for f in as_completed(futures)]
    db.write_batch(conn, results, run_id)    # main thread only
    cleanup_memory(); log_resource_status()
    batch_size = adjust_batch_size(...)
```

---

## Implementeringsrækkefølge

1. **Migration `0011_llm_structured.sql`** — view + de to tabeller.
2. **`step_08_llm_extraction/db.py`** — `fetch_pending`, `log_pending`, `log_finished`, `upsert_structured`.
3. **`step_08_llm_extraction/prompts.py`** — load `document_restructuring.md` + `document_classification.md`.
4. **`step_08_llm_extraction/constants.py`** — tærskler, worker-counts.
5. **`step_08_llm_extraction/extractor.py`** — `process_single_document(task, llm)` med pre-flight token-check.
6. **`run_llm_extraction.py`** — entry point, kategorisering, tier-loop.
7. **Bump `--max-model-len` til 131072** i `docker/vllm/docker-compose.yml`.
8. **Verifikation:** `--dry-run`, derefter `--limit 3 --verbose`.

---

## Åbne spørgsmål

1. Skal `--fresh` også nulstille `done`/`skipped` (helt reset), eller kun `error` (auto-retry)?
2. Skal `llm_structured.structured_md` på sigt erstatte/supplere `docling.llm_attachment` der bruges af `email_summaries.py`?
3. Migration nummer **0011** — fortsæt serien?
