#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/../../.."

# Daily incremental run — --resume hardcoded so files already marked status='done'
# in docling_logging are skipped. To re-process specific files use --sha256 (the
# Python script forces resume=False when --sha256 is set). To re-process from
# scratch, invoke the module directly without --resume:
#   docker compose ... docling python3 -m preprocessing.run_docling
docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.run_docling --resume "$@"
