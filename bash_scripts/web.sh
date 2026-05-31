#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../src/05_application/web"
exec npm run dev -- --port "${PORT:-3000}" --hostname "${HOST:-localhost}"
