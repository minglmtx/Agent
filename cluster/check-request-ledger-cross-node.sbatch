#!/bin/bash
# Submit twice with distinct --nodelist, common output argument, ranks 0 and 1.
# This partition permits one node per job; no API/model/website calls.
#SBATCH --partition=a40
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --gres=gpu:a40:1
#SBATCH --time=00:10:00
#SBATCH --job-name=lab-request-cross-node
#SBATCH --output=/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-request-ledger-cross-node-v1/check-%j.log
set -euo pipefail
unset OPENAI_API_KEY OPENROUTER_API_KEY ANTHROPIC_API_KEY PYTHONPATH PYTHONHOME
export LAB_JOB_OUTPUT_DIRECTORY=/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-request-ledger-cross-node-v1/job-${SLURM_JOB_ID}
source /anvme/workspace/r102bf10-lab-generate-skill/admin/workspace-job-output-20261024/environment.sh
project=/anvme/workspace/r102bf10-lab-generate-skill/code/lab-generate-skill
python_bin=/anvme/workspace/r102bf10-lab-generate-skill/tools/python-releases/lab-skill-20261025-v2/bin/python
export PYTHONPATH="$project/src"
driver="$project/tests/framework/cluster_request_check.py"
exec "$python_bin" -B "$driver" --output "$1" --rank "$2"
