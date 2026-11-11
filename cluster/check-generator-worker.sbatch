#!/bin/bash
#SBATCH --partition=a40
#SBATCH --gres=gpu:a40:1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:15:00
#SBATCH --job-name=lab-generator-worker
#SBATCH --output=/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-core-contracts-v1/generator-worker-%j.log
set -euo pipefail
unset OPENAI_API_KEY OPENROUTER_API_KEY ANTHROPIC_API_KEY PYTHONPATH PYTHONHOME
export LAB_JOB_OUTPUT_DIRECTORY=/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-generator-worker-v1/check-${SLURM_JOB_ID}
source /anvme/workspace/r102bf10-lab-generate-skill/admin/workspace-job-output-20261024/environment.sh
export LAB_WORKER_SOFTWARE_RECEIPT="$1"
project=/anvme/workspace/r102bf10-lab-generate-skill/code/lab-generate-skill
export PYTHONPATH="$project/src"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
cd "$project"
exec /anvme/workspace/r102bf10-lab-generate-skill/tools/python-releases/lab-skill-20261025-v2/bin/python -B -m pytest tests/framework/generator_worker_live.py -q -o "cache_dir=$LAB_JOB_OUTPUT_DIRECTORY/pytest-cache" --junitxml="$LAB_JOB_OUTPUT_DIRECTORY/pytest.xml"
