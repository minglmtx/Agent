#!/bin/bash
# Engineering source freeze only; never activate a runtime release.
#SBATCH --partition=a40
#SBATCH --gres=gpu:a40:1
#SBATCH --cpus-per-task=2
#SBATCH --time=00:15:00
#SBATCH --job-name=lab-artifact-freeze
#SBATCH --output=/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-core-contracts-v1/freeze-%j.log
set -euo pipefail
unset OPENAI_API_KEY OPENROUTER_API_KEY ANTHROPIC_API_KEY PYTHONHOME PYTHONPATH
export LAB_JOB_OUTPUT_DIRECTORY=/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-core-contracts-v1/freeze-${SLURM_JOB_ID}
source /anvme/workspace/r102bf10-lab-generate-skill/admin/workspace-job-output-20261024/environment.sh
project=/anvme/workspace/r102bf10-lab-generate-skill/code/lab-generate-skill
export PYTHONPATH="$project/src"
exec /anvme/workspace/r102bf10-lab-generate-skill/tools/python-releases/lab-skill-20261025-v2/bin/python -B "$project/tests/framework/artifact_freeze_live.py"
