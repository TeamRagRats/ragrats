# Step 9 — LLM Extraction

Sender Docling-genereret Markdown gennem en lokal vLLM-server (Nemotron-3-Nano-30B-A3B-NVFP4) og skriver et struktureret resultat til Postgres.

Bygger oven på `docling.markdown` (skrevet af Step 8).

---

## Hvad scriptet gør

For hver `sha256` i `llm_load_queue`:

1. Kategoriserer dokumentet ud fra `char_count`:
   - `small`  ≤ 30 000 chars  (3 workers, FULL mode)
   - `medium` ≤ 95 000 chars  (2 workers, FULL mode)
   - `large`  ≤ 300 000 chars (1 worker, FULL mode)
   - `huge`   > 300 000 chars (1 worker, CLASSIFY mode med truncation til 25 000 chars)
2. Pre-flight token-budget check mod `--max-model-len 131072` — dokumenter der ville overskride loftet sættes til `skipped`.
3. Kalder vLLM:
   - **FULL** → `document_restructuring.md` system prompt, `max_tokens=8196`
   - **CLASSIFY** → `document_classification.md` system prompt, `max_tokens=512`
4. Skriver resultat til `llm_structured` og status til `llm_logging`.

Tiers processeres sekventielt (small → medium → large → huge); inden for hver tier kører dokumenterne parallelt via `ThreadPoolExecutor`. Workers er thread-safe — kun main thread skriver til Postgres.

---

## Kør steppet

### 1. Start vLLM-serveren

```bash
docker compose -f docker/vllm/docker-compose.yml up -d
```

Første start downloader modellen (~15 GB NVFP4-quantized). Caches persisteres på tværs af genstarter (HF + vLLM + TorchInductor + Triton). Se `docker/vllm/RUN_VLLM.md` for detaljer.

Verificer:
```bash
curl http://localhost:8002/v1/models
```

### 2. Sørg for at migrationen er kørt

```bash
python3 src/sql_migrations/migrate.py
```

Migration `0011_llm_structured.sql` opretter `llm_load_queue` (VIEW), `llm_structured` og `llm_logging`.

### 3. Pre-flight (uden LLM-kald)

```bash
python3 -m preprocessing.run_llm_extraction --dry-run
```

Viser fordeling pr. tier + GPU/RAM-status uden at sende noget til vLLM.

### 4. Test med et par filer

```bash
python3 -m preprocessing.run_llm_extraction --limit 3 --verbose
```

### 5. Fuld kørsel

```bash
python3 -m preprocessing.run_llm_extraction
```

Filer der allerede er `done` eller `skipped` i `llm_logging` filtreres væk. `error`-rækker reprocesseres automatisk.

---

## CLI-flags

| Flag | Default | Beskrivelse |
|---|---|---|
| `--limit N` | None | Cap antal dokumenter (test) |
| `--voyage KEY` | None | Filter på `voyage_key` |
| `--sha256 HASH` | repeatable | Process kun de listede sha256-hashes |
| `--fresh` | False | Slet `error`-rækker i `llm_logging` for matchede sha256s før kørsel (force retry) |
| `--dry-run` | False | Kategoriser + rapporter uden LLM-kald |
| `--max-tokens N` | 8196 | Output-budget for FULL mode |
| `--classify-threshold N` | 300000 | Char-grænse hvor CLASSIFY tager over (-1 = altid FULL) |
| `--batch-size N` | 15 | Batch-størrelse pr. tier (reduceres dynamisk ved GPU/RAM-pres) |
| `--max-workers N` | None | Cap workers på tværs af alle tiers |
| `--temperature F` | 0.1 | Sampling temperature |
| `--verbose` | False | Debug-niveau log |

`DATABASE_URL` og `LLM_BASE_URL` læses fra `.env` / miljø.

---

## Output-skemaer

### `llm_structured` (resultat)

| Kolonne | Type | Note |
|---|---|---|
| `sha256` | CHAR(64) PK | FK → `docling.sha256` |
| `mode` | TEXT | `full` / `classify` |
| `document_type` | TEXT | Parset fra første `#`-overskrift (FULL) eller `DOCUMENT_TYPE:`-linje (CLASSIFY) |
| `structured_md` | TEXT | Hele LLM-output (FULL) eller summary-linjen (CLASSIFY) |
| `input_token_count` | INTEGER | vLLM `prompt_tokens` |
| `output_token_count` | INTEGER | vLLM `completion_tokens` |
| `model_name` | TEXT | Auto-detekteret fra vLLM `/v1/models` |
| `processed_at` | TIMESTAMPTZ | — |

### `llm_logging` (telemetri pr. fil)

`status` ∈ {`pending`, `done`, `error`, `skipped`}; bruges til at filtrere allerede behandlede filer fra `llm_load_queue`.

Indeholder også `started_at`, `finished_at`, `duration_ms`, `error_message`, `gpu_util_pct`, `gpu_mem_pct`, `ram_pct`, `batch_idx`, `run_id`.

---

## Verifikations-queries

```sql
-- Status-fordeling
SELECT status, COUNT(*) FROM llm_logging GROUP BY status;

-- Tier-fordeling
SELECT size_category, mode, COUNT(*)
FROM   llm_logging
GROUP  BY size_category, mode
ORDER  BY size_category;

-- Token-forbrug pr. mode
SELECT mode,
       AVG(input_token_count)::INT AS avg_in,
       AVG(output_token_count)::INT AS avg_out,
       MAX(input_token_count) AS max_in
FROM   llm_structured
GROUP  BY mode;

-- Fejl-detaljer
SELECT sha256, file_path, error_message
FROM   llm_logging
WHERE  status = 'error'
ORDER  BY finished_at DESC
LIMIT  20;
```

---

## Fejlsøgning

| Symptom | Sandsynlig årsag | Fix |
|---|---|---|
| `connection refused` på 8002 | vLLM ikke klar | `curl http://localhost:8002/v1/models`, vent og prøv igen |
| Mange `skipped` med "pre-flight: ..." | Dokumenter overskrider 131k tokens efter trunkering | Sænk `--classify-threshold` så flere dokumenter går CLASSIFY-vejen |
| OOM under inferens | For høj `--gpu-memory-utilization` på vLLM | Sænk i `docker/vllm/docker-compose.yml` (fx 0.75) |
| Langsom large-tier | Forventet — 100k+ tokens på 270 GB/s LPDDR5x tager flere minutter pr. fil | Brug `--limit` ved test |
| Tomt output for FULL mode | Modellen er ramt af `max_tokens=8196` cap uden at slutte | Check `output_token_count` — hvis = 8196, dokumentet er for komplekst til at restrukturere; kør evt. CLASSIFY i stedet |
