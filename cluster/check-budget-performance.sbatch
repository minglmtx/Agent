#!/bin/bash
# Synthetic retained histories on real workspace storage, no paid calls.
#SBATCH --partition=a40
#SBATCH --gres=gpu:a40:1
#SBATCH --cpus-per-task=2
#SBATCH --time=00:15:00
#SBATCH --job-name=lab-budget-performance
#SBATCH --output=/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-core-contracts-v1/budget-performance-%j.log
set -euo pipefail
unset OPENAI_API_KEY OPENROUTER_API_KEY ANTHROPIC_API_KEY PYTHONPATH PYTHONHOME
export LAB_JOB_OUTPUT_DIRECTORY=/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-core-contracts-v1/budget-performance-env-${SLURM_JOB_ID}
source /anvme/workspace/r102bf10-lab-generate-skill/admin/workspace-job-output-20261024/environment.sh
project=/anvme/workspace/r102bf10-lab-generate-skill/code/lab-generate-skill
export PYTHONPATH="$project/src:$project/tests/framework"
exec /anvme/workspace/r102bf10-lab-generate-skill/tools/python-releases/lab-skill-20261025-v2/bin/python -B "$project/tests/framework/budget_performance_check.py" --output "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-core-contracts-v1/budget-performance-${SLURM_JOB_ID}"
