# Start the database

Local Postgres for the voyage mailbox import pipeline. Runs in Docker.

## Connection details

| Field       | Value               |
|-------------|---------------------|
| Host        | `localhost`         |
| Port        | `5433`              |
| User        | `teamragrats`       |
| Password    | `ragrats`           |
| Database    | `ragrats`           |
| Container   | `ragrats_database`  |
| Data volume | `data/postgres/` (repo root) |

Connection string:
```
postgresql://teamragrats:ragrats@localhost:5433/ragrats
```

This is already set as `DATABASE_URL` in `.env`.

> Port `5433` (not the usual `5432`) is deliberate — something else on this
> machine is already bound to `5432`.

## First-time setup

```bash
cd /home/golddigger/Desktop/ragrats/docker/postgres

# 1. Start the container (initializes ../../data/postgres on first run)
docker compose up -d

# 2. Verify it's ready
docker compose logs postgres --tail=20        # look for: "database system is ready to accept connections"

# 3. Create the tables
psql "postgresql://teamragrats:ragrats@localhost:5433/ragrats" \
  -f ../../src/preprocessing/schema.sql
```

Tables created: `emails`, `attachments`, `import_runs`, `step_timings`, `file_counters`.
The schema is idempotent — re-running `psql ... -f schema.sql` is safe.

## Daily use

All `docker compose` commands must be run from `docker/postgres/`:

```bash
cd /home/golddigger/Desktop/ragrats/docker/postgres

docker compose up -d          # start (if stopped)
docker compose stop           # stop without losing data
docker compose ps             # status
docker compose logs -f postgres
```

Connect with psql:
```bash
psql "postgresql://teamragrats:ragrats@localhost:5433/ragrats"
```

Or shell into the container:
```bash
docker exec -it ragrats_database psql -U teamragrats -d ragrats
```

## Resetting the database

Destroys all imported data. The container will re-initialize with the
credentials from `docker-compose.yml` on the next `up`.

```bash
cd /home/golddigger/Desktop/ragrats/docker/postgres
docker compose down
rm -rf ../../data/postgres
docker compose up -d
psql "postgresql://teamragrats:ragrats@localhost:5433/ragrats" \
  -f ../../src/preprocessing/schema.sql
```

## Running the import

Once the DB is up and the schema is applied:

```bash
# Dry run on a single voyage (no DB / disk writes)
python3 src/preprocessing/run_ingest.py --voyage AFRICAN_JUNIPER_1 --dry-run

# Real import, single voyage
python3 src/preprocessing/run_ingest.py --voyage AFRICAN_JUNIPER_1

# Full import
python3 src/preprocessing/run_ingest.py

# Resume after a crash (skips email_ids already in DB)
python3 src/preprocessing/run_ingest.py --resume

# Print per-voyage summary from the DB without importing
python3 src/preprocessing/run_ingest.py --summary-only
```

## Sanity queries

```sql
SELECT voyage_key, count(*) FROM emails GROUP BY 1 ORDER BY 2 DESC;

SELECT thread_id, count(*) FROM emails
WHERE voyage_key = 'AFRICAN_JUNIPER_1'
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

SELECT step_name, duration_ms, rows_in, rows_out, errors
FROM step_timings ORDER BY started_at;

SELECT count(*), pg_size_pretty(sum(size_bytes)) FROM attachments;
```

## Troubleshooting

- **`password authentication failed for user "postgres"`** — you're hitting the wrong server. Our container uses `teamragrats`, not `postgres`, on port `5433`, not `5432`.
- **`connection refused`** — container isn't up. `docker compose up -d` and check `docker compose logs postgres`.
- **Credentials appear ignored after changes** — Postgres only reads `POSTGRES_USER/PASSWORD/DB` on *first* initialization of `./data/postgres/`. To apply new values, stop the container and delete `./data/postgres/` (see "Resetting").
- **Port `5433` already in use** — change the host port in `docker-compose.yml` (`"127.0.0.1:<NEW>:5432"`) and update `DATABASE_URL` in `.env` to match.
