#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "$0")/local-env.sh"
exec "$DEMO_PYTHON" -m mini_claude --max-turns 10 "$@"
