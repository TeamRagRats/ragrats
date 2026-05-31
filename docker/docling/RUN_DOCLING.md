# Kør docling-pipelinen

## Forudsætninger

1. **Postgres er oppe** — se `docker/postgres/START_DATABASE.md`:
   ```bash
   docker compose -f docker/postgres/docker-compose.yml up -d
   ```

2. **Skemaet er oprettet** fra `sql/db.sql`:
   ```bash
   python sql/init_db.py
   ```

3. **Attachments er importeret** (step 01–06 via `run_ingest.py`), så `docling_load_queue`-viewet har rækker.

4. **Docling-image er bygget**:
   ```bash
   docker compose -f docker/docling/docker-compose.yml build
   ```

## Kør pipelinen

**Hverdagskørsel** (anbefalet) — wrapper-scriptet hardkoder `--resume` så filer markeret `status='done'` springes over:
```bash
./src/preprocessing/step_08_docling/run_docling.sh
```

**Direkte invocation** uden wrapper:
```bash
docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.run_docling --resume
```

`DATABASE_URL` overrides `.env`-værdien så containeren rammer postgres-containeren på dens interne netværksnavn (ikke host-localhost).

## CLI-flags

| Flag | Brug | Hvornår |
|---|---|---|
| `--limit N` | Processer kun N filer | Smoke-test, debugging |
| `--voyage <key>` | Filtrér på `voyage_key` | Test én voyage, genkør efter ny import |
| `--batch-size N` | Override default (15) | Tune ved OOM eller langsom GPU |
| `--resume` | Skip filer med `status='done'` i `docling_logging` | Standard ved gen-kørsel (sat af wrapper-scriptet) |
| `--sha256 HASH` (gentages) | Re-processer specifikke filer | Test af enkelte dokumenter; tvinger `resume=False` |
| `--verbose` | DEBUG-logging | Fejlsøgning |

## Typiske kørsler

**Smoke-test — 5 filer:**
```bash
./src/preprocessing/step_08_docling/run_docling.sh --limit 5 --verbose
```

**Én voyage:**
```bash
./src/preprocessing/step_08_docling/run_docling.sh --voyage CAPTAIN_RAVI_1
```

**Re-processer specifikke filer (sha256-filter):**
```bash
./src/preprocessing/step_08_docling/run_docling.sh \
  --sha256 abc123... --sha256 def456...
```

**Re-processer alt fra bund (overskriver eksisterende rækker):**
```bash
# Udelad --resume ved at invokere modulet direkte
docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.run_docling --verbose
```

## Konfiguration

Pipelinen kører Docling med følgende eksplicit valgte high-quality options (`docling_runner.py:build_docling_converter`):

- **Layout:** Heron (`ds4sd/docling-layout-heron`) når installeret Docling-version exposerer den; ellers fallback til default med advarsel.
- **Tabel:** TableFormerMode.ACCURATE + `do_cell_matching=True`.
- **Picture description:** IBM Granite Vision 3.3-2b genererer billed-beskrivelser og indlejrer dem i markdown ved siden af `<!-- image -->` placeholders.
- **GPU:** AcceleratorDevice.AUTO (CUDA på maskiner med NVIDIA-driver).

## Tjek resultatet

```sql
-- Hvor mange filer er processeret?
SELECT status, count(*) FROM docling_logging GROUP BY status;

-- Seneste kørsler
SELECT sha256, duration_ms, char_count, status, error_message
FROM docling_logging ORDER BY finished_at DESC NULLS LAST LIMIT 10;

-- Bekræft markdown er gemt
SELECT count(*) AS rows_with_md FROM docling WHERE markdown IS NOT NULL;
```

## Fejlsøgning

- **`connection refused` mod postgres** → postgres-containeren er ikke oppe, eller `postgres_default`-netværket findes ikke. Start postgres først.
- **`Input missing: /input/…`** → `data/attachment/` er tom eller mount er forkert. Tjek `docker-compose.yml`.
- **GPU ikke detekteret** → containeren kunne ikke reservere NVIDIA-runtime. Kør `docker run --rm --gpus all nvidia/cuda:13.0.0-base-ubuntu22.04 nvidia-smi` for at verificere host-setup.
- **`nvrtc: invalid --gpu-architecture`** → GPU-arkitekturen er for ny til torch-wheelen. Kræver rebuild med nyere torch (se Dockerfile).
- **VLM custom code error (`trust_remote_code=True`)** → en model er skiftet til en der kræver custom kode. Skift `repo_id` i `docling_runner.py` til en standard-loader-kompatibel model (Granite Vision er testet).
