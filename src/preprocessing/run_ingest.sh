#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/../.."

docker compose -f docker/postgres/docker-compose.yml up -d
python3 -m src.preprocessing.run_ingest "$@"
