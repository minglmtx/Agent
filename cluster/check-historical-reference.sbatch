#!/bin/bash
#SBATCH --partition=a40
#SBATCH --gres=gpu:a40:1
#SBATCH --cpus-per-task=2
#SBATCH --time=00:15:00
#SBATCH --job-name=lab-history-read
#SBATCH --output=/anvme/workspace/r102bf10-lab-generate-skill/admin/legacy-reference-cutover-20261026-v1/verify-%j.log
set -euo pipefail
unset OPENAI_API_KEY OPENROUTER_API_KEY ANTHROPIC_API_KEY PYTHONPATH PYTHONHOME
export LAB_JOB_OUTPUT_DIRECTORY=/anvme/workspace/r102bf10-lab-generate-skill/admin/legacy-reference-cutover-20261026-v1/job-${SLURM_JOB_ID}
source /anvme/workspace/r102bf10-lab-generate-skill/admin/workspace-job-output-20261024/environment.sh
project=/anvme/workspace/r102bf10-lab-generate-skill/code/lab-generate-skill
export PYTHONPATH="$project/src"
exec /anvme/workspace/r102bf10-lab-generate-skill/tools/python-releases/lab-skill-20261025-v2/bin/python -B "$project/tests/framework/historical_reference_live.py" "$@"
