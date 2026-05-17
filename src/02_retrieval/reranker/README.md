# Reranker — Qwen3-Reranker-8B

Optional cross-encoder reranking stage that sits **after** step_02 (vector or
hybrid) and reorders the candidate pool by genuine query-document relevance.
RRF orders by rank position; the reranker scores each `(query, chunk)` pair
jointly and can promote a chunk from rank 17 to rank 1 when it's actually the
best match.

Pipeline placement:

```
Query → reformulate → embed → step_01 → step_02 (vector | hybrid) → [reranker] → top_k
```

Off by default — opt in with `--rerank`, same convention as `--hybrid`.

---

## What's implemented

### Infrastructure — `docker/reranker/docker-compose.yml`

New vLLM container `ragrats_reranker` on port **8004**. Serves
`Qwen/Qwen3-Reranker-8B` in `--task score` mode with the
`classifier_from_token=["no","yes"]` override that converts the generative
"yes/no" recipe into a sequence-classification head exposing
`/v1/rerank`. Coexists with `ragrats_vllm` on the same GPU
(`--gpu-memory-utilization 0.35` by default).

### Client — `clients/rerank_client.py`

`RerankClient(base_url, api_key)` — mirrors `EmbedClient`. Auto-detects model
on first contact. `rerank(query, documents, top_n=None)` returns
`list[tuple[int, float]]` `(original_index, relevance_score)` sorted desc.
POSTs to `/v1/rerank` via `urllib` (the `openai` SDK does not surface this
endpoint as a first-class method).

### Python module — `src/02_retrieval/reranker/`

| File | Responsibility |
|---|---|
| `rerank.py` | `rerank_chunks(client, query, chunks, top_k)` — pure function. Sends original query + chunk texts to the client, reorders, sets `similarity = rerank_score`, truncates. |
| `__init__.py` | Re-exports `rerank_chunks` and `DEFAULT_RERANK_OVERSAMPLE = 3`. |

### Logging — `sql_migrations/0082_retrieval_logging_rerank.sql`

Adds four columns to `retrieval_logging`:

- `reranked BOOLEAN NOT NULL DEFAULT FALSE`
- `rerank_model TEXT`
- `rerank_pool INTEGER`  (candidates fed to the reranker)
- `rerank_ms INTEGER`

When `reranked = TRUE`, the `similarity` field inside each chunk in the
existing `chunks` JSONB column is the rerank score — same overload pattern
as BM25 → `ts_rank`.

### CLI flags

Three new flags wired into `run_retrieve.py`, both
`src/04_testing/step_02_retrieval/{chunk_retrieval,e2e_retrieval}/run_test.py`,
and `src/03_generation/run_generation.py`:

| Flag | Effect |
|---|---|
| `--rerank` | Rerank step_02 output with Qwen3-Reranker-8B |
| `--rerank-pool INT` | Candidates fed to the reranker (default: `3 × top_k_2`) |
| `--rerank-url URL` | Reranker base URL (default: `http://localhost:8004/v1`) |

When `--rerank` is on, step_02 oversamples to `--rerank-pool`, the reranker
scores all of them, and the final list is truncated back to `top_k_2`.

### Query routing

Original (non-reformulated) query is sent to the reranker — same reasoning as
BM25: the cross-encoder benefits from the user's exact intent and proper
nouns. The vector side still receives the reformulated query's embedding
when `--reformulate` is set.

---

## How to test that it works

### 1. Container starts and serves

```bash
cd docker/reranker && docker compose up -d
curl http://localhost:8004/v1/models
# expected: data: [{"id": "Qwen/Qwen3-Reranker-8B", ...}]
```

### 2. Client smoke test

```bash
python -c "from clients.rerank_client import RerankClient; \
  r = RerankClient(); \
  print(r.rerank('demurrage claim', ['Port of Rotterdam demurrage invoice', \
  'Vessel schedule for July', 'Demurrage settlement letter']))"
# expected: indices 0 and 2 ranked above index 1, scores in [0, 1]
```

### 3. Migration applied

```sql
\d+ retrieval_logging
-- must include: reranked, rerank_model, rerank_pool, rerank_ms
```

### 4. End-to-end retrieval via the CLI

```bash
# Baseline (vector only)
python src/02_retrieval/run_retrieve.py --query "Appaloosa charterparty"

# Vector + rerank
python src/02_retrieval/run_retrieve.py --query "Appaloosa charterparty" --rerank

# Full stack: hybrid + rerank
python src/02_retrieval/run_retrieve.py --query "Appaloosa charterparty" --hybrid --rerank
```

Sanity checks:

- `--rerank` runs should log a `[rerank] … Xms` line showing the pool reduction.
- Top-3 chunks should change order between `--hybrid` and `--hybrid --rerank`
  for at least some queries — if they're identical for every query, the
  reranker isn't actually contributing.
- `SELECT reranked, rerank_model, rerank_pool, rerank_ms FROM retrieval_logging
  ORDER BY created_at DESC LIMIT 1;` should be populated.

### 5. Recall@k uplift on ground truth

```bash
# Vector only (baseline)
python src/04_testing/step_02_retrieval/chunk_retrieval/run_test.py --top-k 20

# Hybrid
python src/04_testing/step_02_retrieval/chunk_retrieval/run_test.py --top-k 20 --hybrid

# Hybrid + rerank (the full stack)
python src/04_testing/step_02_retrieval/chunk_retrieval/run_test.py --top-k 20 --hybrid --rerank
```

Same flags exist on `e2e_retrieval/run_test.py`. `--hybrid --rerank` should
match or exceed `--hybrid` on MRR for keyword-heavy queries.

### 6. Generation pipeline end-to-end

```bash
python src/03_generation/run_generation.py --query "..." --rerank
```

---

## Scope boundaries

- Reranker runs **only on step_02 output**. Step_01 voyage_key voting is
  unaffected.
- Reranker is **off by default** — pure vector / hybrid behavior is unchanged
  when flags are absent.
- `similarity` on returned chunks is overloaded with the rerank score when
  reranking is on. The pre-rerank score is not preserved.
- `run_generation.py` wires rerank as a wrapper over `retrieve_chunks` (pure
  vector retrieval). The hybrid path is not yet plumbed through `run_query`
  — that's a separate change.
- No reranker-specific test fixtures. Evaluation is done via the existing
  `chunk_retrieval` / `e2e_retrieval` runners with `--rerank`.
