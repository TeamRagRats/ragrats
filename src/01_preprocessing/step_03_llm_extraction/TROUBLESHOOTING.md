# Step 9 — LLM Extraction: Troubleshooting

A living log of issues we have hit during operation, what the symptom was, and what the fix was. Add new entries at the top as they come up.

---

## 0. Watchdog + auto-restart loop (operational tool, not a bug)

`run_llm_extraction.sh` is now a wrapper loop that starts `watchdog.sh` as a sibling process. The watchdog runs every 20s and kills the python orchestrator if:
- the oldest `pending` row in `llm_logging` is older than 3 min (`STUCK_S=180`), or
- `curl /v1/models` fails twice in a row (`API_FAIL_LIMIT=2`).

On trigger: `docker compose restart` on vllm + SIGTERM/SIGKILL to python. The wrapper loop restarts the orchestrator up to 10 times (`LLM_MAX_RESTARTS=10`) or until the queue is drained.

`flock -n` on `/tmp/ragrats_llm_extraction.lock` prevents two terminals from starting the script at the same time (this was the cause of exit 137 on compose-replace at 2026-04-26 01:10).

Tunables via env vars: `WATCHDOG_POLL_S`, `WATCHDOG_STUCK_S`, `WATCHDOG_API_FAIL_LIMIT`, `LLM_MAX_RESTARTS`.

### vLLM memory tuning (same commit as the watchdog)

`docker/vllm/docker-compose.yml` was lowered to `--max-model-len 32768 --gpu-memory-utilization 0.70` (from 131072 / 0.85) to bring unified-memory usage down from 116/121 GiB → ~60–70 GiB. `MODEL_MAX_CONTEXT_TOKENS` in `constants.py` was updated to match so the pre-flight token check matches the server's new ceiling. The medium tier (≤95k chars ≈ 24k tokens) still fits FULL mode with 8k output. If it breaks for very large medium docs, jump to `49152`.

---

## 1. `vllm serve` entrypoint crash — leading `--flag` was interpreted as the command

**Symptom:** Container exited before FastAPI started. The NVIDIA image's entrypoint tried to exec the first token in the `command:` list, and the first token was `--dtype` (a flag) → error.

**Fix:** `docker/vllm/docker-compose.yml` — prepend `vllm serve` to `command:`. Fixed in commit `b38e590`.

---

## 2. vLLM cold-start takes longer than the orchestrator's timeout (300 s)

**Symptom:**
```
INFO  Waiting for vLLM server: http://localhost:8002/v1
ERROR vLLM server not reachable: http://localhost:8002/v1
```
…followed by a graceful exit. The container was actually still loading the model.

**Diagnostics:** the vLLM log shows `init engine (profile, create kv cache, warmup model) took 309.13 seconds` — engine init alone exceeds 300 s. Plus CUDA graph capture and model weights take a total of ~6 min for Nemotron-3-Nano-30B on the first run.

**Fix:** Bumped the `wait_for_server` timeout from 300 → 600 s in `run_llm_extraction.py:303`. The second time it is fast because the caches (`vllm_cache`, `torchinductor_cache`, `triton_cache`, HuggingFace) are warm.

---

## 3. LLM hallucinates "Bill of Lading" on empty documents

**Symptom:** 24 out of 48 rows in `llm_structured` looked identical — all classified as "Bill of Lading" or `[Detected Document Type]`. The user experienced them as "the same document repeated".

**Root cause:** `llm_load_queue` (migration `0011_llm_structured.sql`) only filtered `markdown IS NOT NULL AND TRIM(markdown) <> ''`. That does not catch OCR output consisting solely of `<!-- image -->` placeholders or scrap digits (`13\n13\n13`). With ~14 real characters and a strict schema prompt in `system_prompts/llm_extraction/document_restructuring.md`, the model fabricates a generic shipping document out of nothing.

`fetch_pending` sorts `ORDER BY q.char_count ASC` (`db.py:58`), so `--limit 3` picked the 3 smallest rows — all were `<!-- image -->`-only → all 3 hallucinated as Bill of Lading.

**Fix (3 layers):**
1. New migration `0013_llm_queue_min_content.sql` — the view now requires `LENGTH(REGEXP_REPLACE(markdown, '<!--[^>]*-->|\s+', '', 'g')) >= 50` real characters.
2. Runtime skip in `extractor.py` — `process_single_document` marks rows with `< MIN_CONTENT_CHARS` real chars as `status='skipped'`, reason `insufficient_content`, without calling the LLM.
3. `MIN_CONTENT_CHARS = 50` added in `constants.py`.

**Cleanup of existing bad data:** a SQL block that DELETEs rows where the source markdown has < 50 real characters. Deleted 24 rows from `llm_structured`/`llm_logging`. (See the diff to `plan.md` in `.claude/plans/`.)

---

## 4. vLLM container was SIGTERM'd mid-run — exit 137

**Symptom:**
```
APIConnectionError: Connection error.
```
…on several requests, ~25 s before the container disappeared. The remaining rows hung in `status='pending'`.

**Diagnostics via `docker events --since 1h | grep ragrats_vllm`:**
```
01:10:12  container kill  signal=15  label: com.docker.compose.replace=ragrats_vllm
01:10:22  container kill  signal=9
01:10:22  container die   exitCode=137
```
The label `com.docker.compose.replace=ragrats_vllm` reveals it: a `docker compose up` was run against the vllm project and recreated the container. **Not OOM** (`OOMKilled=false`, `dmesg` clean, 112 GiB free RAM), **not a crash** (logs show a graceful FastAPI shutdown).

Most likely cause: the orchestrator script was run in two terminals at the same time — the second `compose up -d` recreated the running container (config-hash mismatch or compose-version quirk).

**Fix:**
1. Stale-pending recovery: `fetch_pending` (`db.py:48`) now resumes rows that have been `pending` for > 30 min — assuming the container died mid-flight. No manual `UPDATE` needed anymore.
2. Operational rule: do not run `run_llm_extraction.sh` in parallel in multiple terminals.

**Manual unstick (should it happen again before the 30-min timeout):**
```sql
UPDATE llm_logging SET status='error', error_message='vllm_died_midflight'
WHERE status='pending';
```

---

## Suspects from an older repo (not seen yet, but good leads)

Notes from an earlier repo that solved a similar task. Use as a checklist if the vLLM container won't start / dies mysteriously:

### A. Exit code table
| Exit | Meaning |
|------|-----------|
| 0    | Clean exit (graceful shutdown) |
| 1    | General error — check the logs |
| 127  | Command not found — e.g. `vllm` not in PATH in the image |
| 137  | SIGKILL — may be OOM (`OOMKilled=true`) or killed manually (`docker stop`, `compose replace`) |
| 139  | SIGSEGV |

Distinguish OOM from a manual kill via `docker inspect <container> --format '{{.State.OOMKilled}}'` and `docker events --since 1h`.

### B. Possible causes of startup failure

1. **`vllm serve` not in PATH** in `nvcr.io/nvidia/vllm:26.02-py3` → exit 127. Alternative entrypoint: `python3 -m vllm.entrypoints.openai.api_server --model ...`. (We have already checked — `vllm serve` works in this image, but worth checking on image bumps.)
2. **CUDA forward-compat issue** — symptom in the logs: `Using CUDA 13.1 driver version 590.48.01 with kernel driver version 580.142`. The driver is older than the CUDA version → can crash at kernel init on Hopper/Blackwell.
3. **OOM during model load** — Nemotron 30B NVFP4 ≈ 15 GB weights + KV cache for `--max-model-len 131072`. With `--gpu-memory-utilization 0.85` on a GB10 it should be OK, but if the GPU is used at the same time by something else (Docling, embeddings) it can get tight. Check `nvidia-smi` while vLLM starts.
4. **Model download / HF auth** — `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4` may require an HF token or be gated. The logs typically show `401 Unauthorized` or `gated repo`. The HF cache is bind-mounted to `~/.cache/huggingface`, so after the first successful download it is self-sustaining.
5. **`--trust-remote-code` import error** — the model fetches custom Python; it can crash during import. Symptom: a stack trace with `ModuleNotFoundError` or `ImportError` from the model's own code.

### C. Standard diagnostics when vLLM does not respond

```bash
# Status + last exit
docker ps -a | grep ragrats_vllm
docker inspect ragrats_vllm --format 'Started: {{.State.StartedAt}}{{"\n"}}Finished: {{.State.FinishedAt}}{{"\n"}}ExitCode: {{.State.ExitCode}}{{"\n"}}OOMKilled: {{.State.OOMKilled}}'

# Logs (last 200 lines or from the start)
docker logs ragrats_vllm --tail 200
docker logs ragrats_vllm 2>&1 | head -100   # startup

# Who killed it?
docker events --since 1h --until 0s 2>&1 | grep ragrats_vllm

# Is the API up?
curl -s -m 5 http://localhost:8002/v1/models | head

# RAM/GPU/dmesg
free -h
nvidia-smi
sudo dmesg -T | grep -iE "oom|killed" | tail -20
```
