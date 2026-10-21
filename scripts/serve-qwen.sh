#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "$0")/local-env.sh"
export VLLM_USE_V1=1
export VLLM_CACHE_ROOT="$DEMO_STORAGE/cache/vllm-coding-demo"
export TORCHINDUCTOR_CACHE_DIR="$DEMO_STORAGE/cache/torchinductor-coding-demo"
exec "$DEMO_PYTHON" -m vllm.entrypoints.openai.api_server \
  --model "$MINI_CLAUDE_TOKENIZER" --served-model-name "$MINI_CLAUDE_MODEL" \
  --host 127.0.0.1 --port "${DEMO_PORT:-8020}" \
  --max-model-len "$MINI_CLAUDE_CONTEXT_WINDOW" --max-num-seqs 2 \
  --max-num-batched-tokens 16384 --gpu-memory-utilization 0.85 --enforce-eager \
  --enable-auto-tool-choice --tool-call-parser hermes \
  --disable-log-requests "$@"
