# Run the vLLM server

## Prerequisites

1. **NVIDIA Docker runtime is installed** on the Spark machine — verify with:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi
   ```

2. **Enough disk space** — first startup downloads `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4` (~30B parameters) into `~/.cache/huggingface`. Make sure the drive has space before starting.

## Start the server

```bash
docker compose -f docker/vllm/docker-compose.yml up -d
```

The server is ready when `/v1/models` responds — check with:
```bash
curl http://localhost:8002/v1/models
```

First startup takes a while (model download + loading). Subsequent starts take ~1-2 min.

## Stop the server

```bash
docker compose -f docker/vllm/docker-compose.yml down
```

## Run the summaries step

Make sure postgres is running before starting (`docker compose -f docker/postgres/docker-compose.yml up -d`).

With both services running, step 07 works as normal — `LLMClient` automatically hits port 8002:
```bash
python src/preprocessing/run_summaries.py
```

Or with an explicit URL if needed:
```bash
LLM_BASE_URL=http://localhost:8002/v1 python src/preprocessing/run_summaries.py
```

## Troubleshooting

- **`connection refused` on port 8002** → container is not up or model is still loading. Wait and retry `curl`.
- **GPU not detected** → NVIDIA Docker runtime is missing. See prerequisites.
- **OOM during model load** → reduce `--gpu-memory-utilization` in `docker-compose.yml` (e.g. `0.60`).
- **Slow first startup** → model is being downloaded from HuggingFace. It will be cached in `~/.cache/huggingface` afterwards.
