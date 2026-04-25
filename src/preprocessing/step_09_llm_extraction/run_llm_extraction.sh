#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/../../.."

# Daily incremental run — files already marked status='done' or 'skipped' in
# llm_logging are filtered out by fetch_pending(); error-rows are auto-retried.
# Brings up the vLLM container if it isn't already running. The Python
# orchestrator runs on the host and waits up to 300s for vLLM /v1/models
# (cold start downloads/loads the model — can take several minutes).
docker compose -f docker/vllm/docker-compose.yml up -d
python3 src/preprocessing/run_llm_extraction.py "$@"
