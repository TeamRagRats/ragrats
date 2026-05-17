# HNSW `ef_search` — retrieval tuning knob

## What it is

`hnsw.ef_search` is the size of the candidate pool the HNSW index walks
before returning the top-K nearest vectors. Higher = better recall, slower.
pgvector requires `ef_search >= LIMIT`. Postgres' default is **40**.

We expose two independent knobs:

| Knob          | Step                              | Default            |
|---------------|-----------------------------------|--------------------|
| `ef_search_1` | `find_winning_voyage_keys` (vote) | `top_k_1` (500)    |
| `ef_search_2` | `retrieve_chunks` (anchor)        | effective step-2 LIMIT (= `rerank_pool` when `--rerank`, else `top_k_2`) |

Both are set via `SET LOCAL hnsw.ef_search = …` at the top of each step's
function, so step 2 never silently inherits step 1's value (or falls back to
Postgres' 40 when step 1 is skipped via `--no-voyage-key`).

## Why this matters

Before this change, `ef_search` was implicitly `= top_k_1`, set only inside
step 1. Two consequences:

1. **Coupled to `top_k_1`** — no way to sweep `ef_search` independently of
   the vote width.
2. **Latent recall bug** — if step 1 was skipped, or step 2 ran in a fresh
   transaction, step 2 silently used `ef_search=40`. Worse: with
   `--rerank --rerank-pool 200`, step 2's LIMIT was 200 but pgvector would
   walk only 40 candidates first — most of the pool came from a tiny seed.

Both are fixed: each step now sets its own `ef_search` explicitly.

## How to use

### Online (production / CLI)

```bash
# default behaviour — identical to before
python src/02_retrieval/run_retrieve.py --query "..."

# override either knob
python src/02_retrieval/run_retrieve.py --query "..." \
    --ef-search-1 1000 --ef-search-2 200

# fixes the latent step-2 bug when step 1 is skipped
python src/02_retrieval/run_retrieve.py --query "..." \
    --no-voyage-key --ef-search-2 200
```

Same flags exist on `src/03_generation/run_generation.py`, and `run_query()`
takes `ef_search_1` / `ef_search_2` kwargs.

### Sweep (test harness)

`src/04_testing/step_02_retrieval/e2e_retrieval/run_test.py`:

```bash
# fix top-k, sweep ef_search_1
for ef in 200 500 1000 2000; do
    python run_test.py --top-k-1 500 --top-k-2 20 --ef-search-1 $ef
done
```

Isolated step runners (`voyage_key_retrieval/run_test.py`,
`chunk_retrieval/run_test.py`) each accept a single `--ef-search` flag —
step 1 only and step 2 only respectively.

## Logged values

`retrieval_logging` (migration `0083`) gains two nullable columns:

| Column        | Meaning                                                     |
|---------------|-------------------------------------------------------------|
| `ef_search_1` | value used in step 1 — `NULL` when step 1 was skipped       |
| `ef_search_2` | value used in step 2                                        |

When you don't pass the flag, the logged value equals the effective default
(`top_k_1` / step-2 LIMIT), so historical comparisons are unambiguous.

## Out of scope

- `m` and `ef_construction` (index build-time params) are still hardcoded in
  `sql_migrations/0011_chunks.sql`. Tuning them requires a full index rebuild.
- No FastAPI/UI exposure — `/chat/message` uses defaults via `run_query()`.
- Picking the new "best" default is an empirical follow-up: run the sweep,
  inspect per-category recall vs. latency, then bump the defaults in the
  three CLI runners (`run_retrieve.py`, `run_generation.py`, and the test
  harnesses) plus the `top_k_1=500 → ef_search_1=…` line if it diverges.
