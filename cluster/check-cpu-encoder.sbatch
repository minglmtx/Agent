#!/bin/bash
#SBATCH --partition=a40
#SBATCH --gres=gpu:a40:1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:15:00
#SBATCH --job-name=lab-cpu-encoder
#SBATCH --output=/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-encoder-v1/check-%j.log
set -euo pipefail
unset OPENAI_API_KEY OPENROUTER_API_KEY ANTHROPIC_API_KEY PYTHONPATH PYTHONHOME
export PYTHONPATH=/anvme/workspace/r102bf10-lab-generate-skill/code/lab-generate-skill/src
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
exec /anvme/workspace/r102bf10-lab-generate-skill/tools/python-releases/lab-skill-20261025-v2/bin/python -B /anvme/workspace/r102bf10-lab-generate-skill/code/lab-generate-skill/tests/framework/encoder_live_check.py "$@"
