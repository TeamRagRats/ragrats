#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/../../.."

docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.run_docling --resume "$@"
