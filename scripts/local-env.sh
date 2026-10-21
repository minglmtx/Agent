#!/usr/bin/env bash
# Source from the project scripts. Does not change HOME or other project environments.
DEMO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_STORAGE="${DEMO_STORAGE:-$DEMO_ROOT/.demo-runtime}"
if [[ -z "${DEMO_PYTHON:-}" ]]; then
  if [[ -x "$DEMO_ROOT/.venv/bin/python" ]]; then
    DEMO_PYTHON="$DEMO_ROOT/.venv/bin/python"
  else
    DEMO_PYTHON=python3
  fi
fi
export MINI_CLAUDE_STATE_DIR="${MINI_CLAUDE_STATE_DIR:-$DEMO_STORAGE/outputs/coding-agent-demo/state}"
export MINI_CLAUDE_MODEL="${MINI_CLAUDE_MODEL:-qwen3-8b-local}"
export MINI_CLAUDE_LOCAL_MODEL=1
export MINI_CLAUDE_CONTEXT_WINDOW=16384
export MINI_CLAUDE_MAX_OUTPUT_TOKENS=2048
export MINI_CLAUDE_TOKENIZER="${DEMO_MODEL_PATH:-$DEMO_STORAGE/models/Qwen3-8B}"
export MINI_CLAUDE_DISABLE_MEMORY=1
export MINI_CLAUDE_SDK_MAX_RETRIES=0
export OPENAI_BASE_URL="${DEMO_API_BASE:-http://127.0.0.1:8020/v1}"
export OPENAI_API_KEY=local-demo
unset ANTHROPIC_API_KEY ANTHROPIC_BASE_URL
export PYTHONPATH="$DEMO_ROOT/python${PYTHONPATH:+:$PYTHONPATH}"
export HF_HOME="$DEMO_STORAGE/cache/huggingface"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}" OPENBLAS_NUM_THREADS=1
umask 077
