#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/../../.."

# Spec-variant launcher (branch docling_spec_changes). No --resume hardcoded so
# --sha256 re-runs work cleanly. Add --resume yourself if you want to skip done files.
docker compose -f docker/docling/docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql://teamragrats:ragrats@ragrats_database:5432/ragrats \
  docling python3 -m preprocessing.run_docling_spec "$@"
