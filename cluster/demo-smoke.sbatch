#!/usr/bin/env bash
#SBATCH --job-name=coding-demo-smoke
#SBATCH --partition=a40
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:45:00
#SBATCH --output=coding-demo-%j.log
set -euo pipefail
MODE="${1:-dev}"
case "$MODE" in dev|final) ;; *) echo "Usage: sbatch $0 [dev|final]" >&2; exit 2 ;; esac
DEMO_SOURCE_ROOT="${DEMO_SOURCE_ROOT:-$SLURM_SUBMIT_DIR}"
source "$DEMO_SOURCE_ROOT/scripts/local-env.sh"
export DEMO_PORT=8020
export DEMO_API_BASE="http://127.0.0.1:$DEMO_PORT/v1"
export OPENAI_BASE_URL="$DEMO_API_BASE"
RUN_DIR="$DEMO_STORAGE/outputs/coding-agent-demo/gpu-${SLURM_JOB_ID}"
mkdir -p "$RUN_DIR"
# Record code identity, including uncommitted Python changes.
git -C "$DEMO_ROOT" rev-parse HEAD > "$RUN_DIR/upstream-commit.txt"
git -C "$DEMO_ROOT" diff > "$RUN_DIR/changes.patch"
# Include new/untracked modules too, and run the copied code throughout this job.
mkdir -p "$RUN_DIR/code"
cp -a "$DEMO_ROOT/python" "$DEMO_ROOT/scripts" "$RUN_DIR/code/"
export DEMO_STORAGE DEMO_PYTHON
source "$RUN_DIR/code/scripts/local-env.sh"
setsid bash "$DEMO_ROOT/scripts/serve-qwen.sh" > "$RUN_DIR/server.log" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill -TERM -- "-$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
export RUN_DIR SERVER_PID
"$DEMO_PYTHON" - <<'PY'
import json, os, time, urllib.request
deadline = time.monotonic() + 600
while time.monotonic() < deadline:
    try:
        os.kill(int(os.environ["SERVER_PID"]), 0)
    except ProcessLookupError:
        raise SystemExit("Model server exited; inspect server.log")
    try:
        with urllib.request.urlopen(os.environ["OPENAI_BASE_URL"] + "/models", timeout=2) as r:
            result = json.load(r)
        assert any(x["id"] == os.environ["MINI_CLAUDE_MODEL"] for x in result["data"])
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("Model startup exceeded 600 seconds")
PY
SPLIT=dev
if [[ "$MODE" == final ]]; then SPLIT=test; fi
"$DEMO_PYTHON" "$DEMO_ROOT/scripts/run_demo_tasks.py" \
  --split "$SPLIT" --workers 2 --output "$RUN_DIR/tasks"
if [[ "$MODE" == final ]]; then
  # Two requests at a time; reuse the already loaded server.
  "$DEMO_PYTHON" "$DEMO_ROOT/scripts/check_summary_demo.py" --output "$RUN_DIR/summary-check"
fi
