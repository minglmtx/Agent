#!/bin/bash
#SBATCH --job-name=checkout-timeout-replay
#SBATCH --partition=a100mig
#SBATCH --cpus-per-task=4
#SBATCH --time=00:20:00
#SBATCH --array=0-1%2
#SBATCH --export=NONE
#SBATCH --output=/home/atuin/r102bf/r102bf10/lmtx/logs/checkout-timeout-replay-%A_%a.log
set -euo pipefail
unset SLURM_EXPORT_ENV
source /home/atuin/r102bf/r102bf10/lmtx/setup-alex.sh
unset OPENROUTER_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY
export APPTAINER_NV=false PYTHONPATH="$LAB_SKILL_ROOT/src:$LAB_SKILL_ROOT/scripts" OMP_NUM_THREADS=4 LAB_PERIODIC_STACK_DUMP_SECONDS=30
export LAB_BROWSER_ACTION_TIMEOUT_MS=5000 ADMIN_AX_POLICY=viewport-v1
base="$LMTX_ROOT/outputs/other-sites-validation-v1"
out="$base/checkout-timeout-replay-$SLURM_ARRAY_JOB_ID/$SLURM_ARRAY_TASK_ID"
python "$LAB_SKILL_ROOT/scripts/run_guarded_runtime.py" --state "$out/watchdog.json" --startup-seconds 180 -- python "$LAB_SKILL_ROOT/scripts/replay_checkout_timeout.py" --root "$LMTX_ROOT" --wave "$base/shopping-checkout-wave1" --source "$base/shopping-checkout-wave1/actor/0/e13dd61bf81912fc20ef" --out "$out/replay"
