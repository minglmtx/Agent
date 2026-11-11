#!/bin/bash
#SBATCH --job-name=stage1-reset-check
#SBATCH --partition=a100mig
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:30:00
#SBATCH --export=NONE
#SBATCH --output=/home/atuin/r102bf/r102bf10/lmtx/logs/stage1-reset-%j.log
set -euo pipefail
unset SLURM_EXPORT_ENV
source /home/atuin/r102bf/r102bf10/lmtx/setup-alex.sh
unset OPENROUTER_API_KEY OPENAI_API_KEY
export CUDA_VISIBLE_DEVICES="" APPTAINER_NV=false
exec python "$LAB_SKILL_ROOT/cluster/check-stage1-reset.py"
