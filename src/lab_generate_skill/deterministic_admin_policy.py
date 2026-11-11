"""Explicit online task exclusions; never deletes source trajectories or skills."""
import json
from pathlib import Path
def require_local_task(task_id):
    policy=json.loads((Path(__file__).resolve().parents[2]/'configs/admin-deterministic-scope-v1.json').read_text())
    if task_id in policy['excluded_tasks']:raise ValueError('excluded_nondeterministic_external_task:'+task_id)
