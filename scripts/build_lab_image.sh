#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run --no-env-file --frozen --no-sync --offline python scripts/build_lab_image.py "$@"
