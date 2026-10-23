#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker build --tag headroom-lab:py312-cu124 lab-image
