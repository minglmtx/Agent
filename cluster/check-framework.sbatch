#!/bin/bash
# Reusable CPU checks on a compute allocation (cluster requires a GPU resource).
#SBATCH --partition=a40
#SBATCH --gres=gpu:a40:1
#SBATCH --cpus-per-task=2
#SBATCH --time=00:15:00
#SBATCH --job-name=lab-framework-check
#SBATCH --output=/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-core-contracts-v1/check-%j.log
set -euo pipefail
unset OPENAI_API_KEY OPENROUTER_API_KEY ANTHROPIC_API_KEY PYTHONPATH PYTHONHOME
export LAB_JOB_OUTPUT_DIRECTORY=/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-core-contracts-v1/check-${SLURM_JOB_ID}
source /anvme/workspace/r102bf10-lab-generate-skill/admin/workspace-job-output-20261024/environment.sh
project=/anvme/workspace/r102bf10-lab-generate-skill/code/lab-generate-skill
python_bin=/anvme/workspace/r102bf10-lab-generate-skill/tools/python-releases/lab-skill-20261025-v2/bin/python
export PYTHONPATH="$project/tools:$project/src:/anvme/workspace/r102bf10-lab-generate-skill/tools/development-checks/mypy-1.15.0"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
exec "$python_bin" -B "$project/tools/check_framework.py" --output "$LAB_JOB_OUTPUT_DIRECTORY" "$@"
