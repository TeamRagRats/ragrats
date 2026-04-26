# Step 9 — LLM Extraction: Troubleshooting

Levende noter over fejl vi er stødt på under driften, hvad symptomet var, og hvad fix'et var. Tilføj nye entries i toppen efterhånden som de dukker op.

---

## 0. Watchdog + auto-restart loop (drift-værktøj, ikke en fejl)

`run_llm_extraction.sh` er nu en wrapper-loop der starter `watchdog.sh` som søsterproces. Watchdog'en kører hvert 20s og dræber python-orchestratoren hvis:
- ældste `pending` row i `llm_logging` er ældre end 3 min (`STUCK_S=180`), eller
- `curl /v1/models` fejler 2 gange i træk (`API_FAIL_LIMIT=2`).

Ved trigger: `docker compose restart` på vllm + SIGTERM/SIGKILL til python. Wrapper-loopen restarter orchestratoren op til 10 gange (`LLM_MAX_RESTARTS=10`) eller indtil køen er drænet.

`flock -n` på `/tmp/ragrats_llm_extraction.lock` forhindrer at to terminaler kan starte scriptet samtidig (var årsagen til exit 137 ved compose-replace 2026-04-26 01:10).

Tunables via env-vars: `WATCHDOG_POLL_S`, `WATCHDOG_STUCK_S`, `WATCHDOG_API_FAIL_LIMIT`, `LLM_MAX_RESTARTS`.

### vLLM memory tuning (samme commit som watchdog)

`docker/vllm/docker-compose.yml` blev sænket til `--max-model-len 32768 --gpu-memory-utilization 0.70` (fra 131072 / 0.85) for at sænke unified-memory forbruget fra 116/121 GiB → ~60–70 GiB. `MODEL_MAX_CONTEXT_TOKENS` i `constants.py` er fulgt med så pre-flight token-checket matcher serverens nye loft. Medium-tier (≤95k chars ≈ 24k tokens) fitter stadig FULL mode med 8k output. Hvis den knækker for store medium-docs, hop til `49152`.

---

## 1. `vllm serve` entrypoint crash — leading `--flag` blev tolket som command

**Symptom:** Container exited før FastAPI startede. NVIDIA-imagets entrypoint forsøgte at exec'e første token i `command:` listen, og første token var `--dtype` (et flag) → fejl.

**Fix:** `docker/vllm/docker-compose.yml` — prepend `vllm serve` til `command:`. Fix i commit `b38e590`.

---

## 2. vLLM cold-start tager længere end orchestratorens timeout (300 s)

**Symptom:**
```
INFO  Waiting for vLLM server: http://localhost:8002/v1
ERROR vLLM server not reachable: http://localhost:8002/v1
```
…fulgt af graceful exit. Containeren var i virkeligheden ved at loade modellen.

**Diagnostik:** vLLM-loggen viser `init engine (profile, create kv cache, warmup model) took 309.13 seconds` — alene engine-init overskrider 300 s. Plus CUDA-graf-capture og model-vægte tager total ~6 min for Nemotron-3-Nano-30B på første kørsel.

**Fix:** Bumpede `wait_for_server` timeout fra 300 → 600 s i `run_llm_extraction.py:303`. Anden gang er det hurtigt fordi caches (`vllm_cache`, `torchinductor_cache`, `triton_cache`, HuggingFace) er warm.

---

## 3. LLM hallucinerer "Bill of Lading" på tomme dokumenter

**Symptom:** 24 ud af 48 rows i `llm_structured` så identiske ud — alle klassificeret som "Bill of Lading" eller `[Detected Document Type]`. Brugeren oplevede dem som "samme dokument gentaget".

**Root cause:** `llm_load_queue` (migration `0011_llm_structured.sql`) filtrerede kun `markdown IS NOT NULL AND TRIM(markdown) <> ''`. Det fanger ikke OCR-output bestående udelukkende af `<!-- image -->`-placeholders eller scrap-cifre (`13\n13\n13`). Med ~14 reelle tegn og en streng schema-prompt i `system_prompts/llm_extraction/document_restructuring.md`, fabrikerer modellen et generisk shippingdokument fra ingenting.

`fetch_pending` sorterer `ORDER BY q.char_count ASC` (`db.py:58`), så `--limit 3` plukkede de 3 mindste rows — alle var `<!-- image -->`-only → alle 3 hallucinerede som Bill of Lading.

**Fix (3 lag):**
1. Ny migration `0013_llm_queue_min_content.sql` — view kræver nu `LENGTH(REGEXP_REPLACE(markdown, '<!--[^>]*-->|\s+', '', 'g')) >= 50` reelle tegn.
2. Runtime-skip i `extractor.py` — `process_single_document` markerer rows med `< MIN_CONTENT_CHARS` real chars som `status='skipped'`, reason `insufficient_content`, uden at kalde LLM.
3. `MIN_CONTENT_CHARS = 50` tilføjet i `constants.py`.

**Cleanup af eksisterende bad data:** SQL-blok der DELETE'r rows hvor source-markdown < 50 reelle tegn. Slettede 24 rows fra `llm_structured`/`llm_logging`. (Se diff til `plan.md` i `.claude/plans/`.)

---

## 4. vLLM-container blev SIGTERM'd midt i kørsel — exit 137

**Symptom:**
```
APIConnectionError: Connection error.
```
…på flere requests, ~25 s før containeren forsvandt. Resterende rows hang i `status='pending'`.

**Diagnostik via `docker events --since 1h | grep ragrats_vllm`:**
```
01:10:12  container kill  signal=15  label: com.docker.compose.replace=ragrats_vllm
01:10:22  container kill  signal=9
01:10:22  container die   exitCode=137
```
Labelen `com.docker.compose.replace=ragrats_vllm` afslører: et `docker compose up` blev kørt mod vllm-projektet og recreated containeren. **Ikke OOM** (`OOMKilled=false`, `dmesg` ren, 112 GiB fri RAM), **ikke crash** (logs viser graceful FastAPI shutdown).

Mest sandsynlig årsag: orchestrator-scriptet blev kørt i to terminaler samtidigt — det andet `compose up -d` recreatede den kørende container (config-hash mismatch eller compose-version-quirk).

**Fix:**
1. Stale-pending recovery: `fetch_pending` (`db.py:48`) genoptager nu rows der står som `pending` i > 30 min — antager at containeren er død mid-flight. Ingen manuel `UPDATE` nødvendig længere.
2. Operationel regel: kør ikke `run_llm_extraction.sh` parallelt i flere terminaler.

**Manuelt unstick (hvis det skulle ske igen før 30-min-timeoutet):**
```sql
UPDATE llm_logging SET status='error', error_message='vllm_died_midflight'
WHERE status='pending';
```

---

## Mistænkte fra ældre repo (endnu ikke set, men gode ledetråde)

Noter fra et tidligere repo der løste lignende opgave. Brug som tjekliste hvis vLLM-containeren ikke vil starte / dør på mystisk vis:

### A. Exit code-tabel
| Exit | Betydning |
|------|-----------|
| 0    | Ren exit (graceful shutdown) |
| 1    | Generel fejl — tjek logs |
| 127  | Command not found — fx `vllm` ikke i PATH i imaget |
| 137  | SIGKILL — kan være OOM (`OOMKilled=true`) eller manuelt dræbt (`docker stop`, `compose replace`) |
| 139  | SIGSEGV |

Skel mellem OOM og manual kill via `docker inspect <container> --format '{{.State.OOMKilled}}'` og `docker events --since 1h`.

### B. Mulige årsager til startup-fejl

1. **`vllm serve` ikke i PATH** i `nvcr.io/nvidia/vllm:26.02-py3` → exit 127. Alternativ entrypoint: `python3 -m vllm.entrypoints.openai.api_server --model ...`. (Vi har allerede tjekket — `vllm serve` virker i dette image, men værd at tjekke ved image-bumps.)
2. **CUDA forward-compat issue** — symptom i logs: `Using CUDA 13.1 driver version 590.48.01 with kernel driver version 580.142`. Driveren er ældre end CUDA-versionen → kan crashe ved kernel-init på Hopper/Blackwell.
3. **OOM under model-load** — Nemotron 30B NVFP4 ≈ 15 GB vægte + KV-cache for `--max-model-len 131072`. Med `--gpu-memory-utilization 0.85` på en GB10 burde det være OK, men hvis GPU bruges samtidig af andet (Docling, embeddings) kan det knibe. Tjek `nvidia-smi` mens vLLM starter.
4. **Model-download / HF-auth** — `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4` kan kræve HF-token eller være gated. Logs viser typisk `401 Unauthorized` eller `gated repo`. HF-cache er bind-mountet til `~/.cache/huggingface`, så efter første succesfulde download er det selvopretholdt.
5. **`--trust-remote-code` import-fejl** — modellen henter custom Python; kan crashe under import. Symptom: stack trace med `ModuleNotFoundError` eller `ImportError` fra modellens egen kode.

### C. Standard-diagnostik når vLLM ikke svarer

```bash
# Status + sidste exit
docker ps -a | grep ragrats_vllm
docker inspect ragrats_vllm --format 'Started: {{.State.StartedAt}}{{"\n"}}Finished: {{.State.FinishedAt}}{{"\n"}}ExitCode: {{.State.ExitCode}}{{"\n"}}OOMKilled: {{.State.OOMKilled}}'

# Logs (sidste 200 linjer eller fra starten)
docker logs ragrats_vllm --tail 200
docker logs ragrats_vllm 2>&1 | head -100   # opstart

# Hvem dræbte den?
docker events --since 1h --until 0s 2>&1 | grep ragrats_vllm

# Er API'et oppe?
curl -s -m 5 http://localhost:8002/v1/models | head

# RAM/GPU/dmesg
free -h
nvidia-smi
sudo dmesg -T | grep -iE "oom|killed" | tail -20
```
