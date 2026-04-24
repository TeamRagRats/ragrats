# Kør docling-pipelinen

## Forudsætninger

1. **Postgres er oppe** — se `docker/postgres/START_DATABASE.md`:
   ```bash
   docker compose -f docker/postgres/docker-compose.yml up -d
   ```

2. **Migrationer er kørt** (inkl. `0004_docling_revision.sql`):
   ```bash
   python src/preprocessing/sql_migrations/migrate.py
   ```

3. **Attachments er importeret** (step 01–06 via `run_ingest.py`), så `docling_load_queue`-viewet har rækker.

4. **Docling-image er bygget**:
   ```bash
   docker compose -f docker/docling/docker-compose.yml build
   ```

## Kør pipelinen

Basale kørsel — alle uprocesserede filer:
```bash
docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.step_08_docling.run_docling --resume
```

`DATABASE_URL` overrides `.env`-værdien så containeren rammer postgres-containeren på dens interne netværksnavn (ikke host-localhost).

## CLI-flags

| Flag | Brug | Hvornår |
|---|---|---|
| `--limit N` | Processer kun N filer | Smoke-test, debugging |
| `--voyage <key>` | Filtrér på `voyage_key` | Test én voyage, genkør efter ny import |
| `--batch-size N` | Override default (15) | Tune ved OOM eller langsom GPU |
| `--resume` | Skip filer med `status='done'` i `docling_logging` | Standard ved gen-kørsel; uden flaget re-processeres alt |
| `--verbose` | DEBUG-logging | Fejlsøgning |

## Typiske kørsler

**Smoke-test — 5 filer, alle voyages:**
```bash
docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.step_08_docling.run_docling --limit 5
```

**Én voyage, fuld kørsel:**
```bash
docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.step_08_docling.run_docling \
  --voyage CAPTAIN_RAVI_1 --resume
```

**Fuld produktion — alle voyages, genstartsvenlig:**
```bash
docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.step_08_docling.run_docling --resume
```

**Re-processer alt (fx efter schema-ændring):**
```bash
# udeladt --resume
docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.step_08_docling.run_docling
```

## Tjek resultatet

```sql
-- Hvor mange filer er processeret?
SELECT status, count(*) FROM docling_logging GROUP BY status;

-- Seneste kørsler
SELECT sha256, duration_ms, char_count, status, error_message
FROM docling_logging ORDER BY finished_at DESC NULLS LAST LIMIT 10;

-- Bekræft markdown + JSON er gemt
SELECT count(*) AS md, count(docling_document) AS json FROM docling;
```

## Fejlsøgning

- **`connection refused` mod postgres** → postgres-containeren er ikke oppe, eller `postgres_default`-netværket findes ikke. Start postgres først.
- **`Input missing: /input/…`** → `data/attachment/` er tom eller mount er forkert. Tjek `docker-compose.yml`.
- **GPU ikke detekteret** → containeren kunne ikke reservere NVIDIA-runtime. Kør `docker run --rm --gpus all nvidia/cuda:13.0.0-base-ubuntu22.04 nvidia-smi` for at verificere host-setup.
- **`nvrtc: invalid --gpu-architecture`** → GPU-arkitekturen er for ny til torch-wheelen. Kræver rebuild med nyere torch (se Dockerfile).
