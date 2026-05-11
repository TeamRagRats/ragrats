#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../src/05_application/api"
exec uvicorn main:app --reload --host 0.0.0.0 --port 8001
