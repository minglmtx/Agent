"""Explicit local-reward bridge; a trace cannot select its own admission reviewer.

The caller supplies a frozen contract and a trusted, family-specific execution
reviewer. That reviewer must check the qualified runner, reset/baseline evidence,
and native judgment. This module checks their binding to the actual skill input.
It does not turn a source label or an actor's success claim into a reward.
"""
from copy import deepcopy
import json
from pathlib import Path

from .generator_sft import file_hash, fingerprint, first_observation
from .schemas import CompactSkill
from .stage1_execution_steps import METRIC,selection_steps,require_metric


def read_pinned_json(ref):
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ValueError("Expected a pinned evidence file")
    path = Path(ref["path"])
    if not path.is_absolute() or file_hash(path) != ref["sha256"]:
        raise ValueError("Local execution evidence changed")
    return json.loads(path.read_text())


class LocalRolloutValidator:
    """An explicit capability supplied by the driver, never imported from data."""

    def __init__(self, contract_ref, *, review_execution):
        if not callable(review_execution):
            raise ValueError("A trusted native execution reviewer is required")
        self.contract_ref = deepcopy(contract_ref)
        self.contract = read_pinned_json(contract_ref)
        self.contract_sha256 = contract_ref["sha256"]
        self.review_execution = review_execution
        required = {
            "version", "task_id", "source_task_id", "runtime_task_id", "domain",
            "public_goal", "website_snapshot_id", "runtime_capsule_sha256",
            "evaluator_version", "output_purpose", "teacher_mode",
        }
        if set(self.contract) != required or self.contract["version"] != "local-stage1-contract-v1":
            raise ValueError("Unsupported local reward contract")
        if not all(isinstance(v, str) and v.strip() for v in self.contract.values()):
            raise ValueError("Incomplete local reward contract")
        # This candidate qualifies the no-paid-API pilot only. Enabling paid
        # construction requires a separately reviewed driver/import contract.
        if (self.contract["output_purpose"], self.contract["teacher_mode"]) != (
            "engineering_pilot", "local_replacement"
        ):
            raise ValueError("Local reward bridge currently permits engineering pilot only")

    def validate_context(self, task, start=None, purpose=None):
        if read_pinned_json(self.contract_ref) != self.contract:
            raise ValueError("Local reward contract changed")
        c = self.contract
        if task["task_id"] != c["task_id"] or task["domain"] != c["domain"]:
            raise ValueError("Active task/domain differs from local reward contract")
        if purpose is not None and purpose != c["output_purpose"]:
            raise ValueError("Local reward output purpose mismatch")
        if start is not None:
            if start["task"] != c["public_goal"] or start["website_snapshot_id"] != c["website_snapshot_id"]:
                raise ValueError("Local task/snapshot differs from admitted contract")
            if start.get("observation_policy", "identity") != "identity":
                raise ValueError("Local initial-observation normalization is not admitted")

    def __call__(self, trace, task, start, skill):
        self.validate_context(task, start)
        skill = CompactSkill.model_validate(skill).model_dump()
        c = self.contract
        if trace.get("error") or trace.get("evaluation_outcome") not in ("correct", "incorrect"):
            raise ValueError("Unscored or runtime-failed local rollout is not a negative")
        if trace["task_id"] != c["runtime_task_id"] or trace["domain"] != c["domain"]:
            raise ValueError("Runtime task/domain mismatch")
        if trace["task_instruction"] != c["public_goal"]:
            raise ValueError("Local rollout public goal mismatch")
        if first_observation(trace) != start["initial_observation"]:
            raise ValueError("Reset did not reproduce the same initial observation")
        p = trace.get("provenance", {})
        if (p.get("mode"), p.get("outcome_source"), p.get("local_evaluator_version")) != (
            "online", "local_task_evaluator", c["evaluator_version"]
        ):
            raise ValueError("Not an admitted local evaluator result")
        if p.get("website_snapshot_id") != c["website_snapshot_id"]:
            raise ValueError("Local rollout snapshot mismatch")
        if p.get("generated_skill_sha256") != fingerprint(skill):
            raise ValueError("Local rollout skill hash mismatch")
        receipt = read_pinned_json(p.get("local_execution_evidence"))
        for key in ("runtime_capsule_sha256", "source_task_id", "task_id",
                    "runtime_task_id", "website_snapshot_id"):
            if receipt.get(key) != c[key]:
                raise ValueError("Local execution receipt identity mismatch: " + key)
        if receipt.get("contract_sha256") != self.contract_sha256:
            raise ValueError("Execution did not use the frozen local contract")
        refs = receipt.get("artifacts", {})
        if not {"scored_trace", "first_request", "result"} <= refs.keys():
            raise ValueError("Incomplete local execution artifacts")
        artifacts = {name: read_pinned_json(ref) for name, ref in refs.items()}
        original = deepcopy(trace)
        original["provenance"].pop("local_execution_evidence", None)
        if artifacts["scored_trace"] != original:
            raise ValueError("Stage-1 trace differs from original native scored trace")
        request = artifacts["first_request"]
        if request.get("status") != "complete":
            raise ValueError("No completed actual actor request")
        users = [m for m in request.get("messages", []) if m.get("role") == "user"]
        if not users:
            raise ValueError("Actual actor request has no user observation")
        body = json.loads(users[-1]["content"])
        sent = body.get("retrieved_skills")
        if not isinstance(sent, list) or len(sent) != 1 or json.loads(sent[0]) != skill:
            raise ValueError("Actual actor request did not contain the exact generated skill")
        if body.get("observation") != start["initial_observation"]:
            raise ValueError("Actual actor request and initial observation differ")
        # The reviewer is trusted driver code. It must independently inspect
        # artifact contents, not accept `passed` flags supplied by the trace.
        reviewed = self.review_execution(deepcopy(c), deepcopy(receipt), artifacts)
        if not isinstance(reviewed, dict) or any(reviewed.get(k) is not True for k in (
            "execution_complete", "runtime_verified", "initial_state_verified"
        )):
            raise ValueError("Native execution/runtime/reset review incomplete")
        judgment = reviewed.get("judgment", {})
        if judgment != artifacts["result"].get("evaluation"):
            raise ValueError("Reviewed native judgment differs from saved execution result")
        reward = judgment.get("reward")
        if type(reward) not in (int, float) or reward not in (0, 1):
            raise ValueError("Native judgment is not a binary business outcome")
        success = judgment.get("status") == "success"
        if judgment.get("status") not in ("success", "failure") or success != (reward == 1):
            raise ValueError("Native judgment status/reward mismatch")
        if judgment.get("version") != c["evaluator_version"]:
            raise ValueError("Reviewed evaluator version mismatch")
        actual_reward = trace.get("task_output", {}).get("reward")
        if type(actual_reward) not in (int, float) or actual_reward != reward:
            raise ValueError("Trace/native reward mismatch")
        if (trace["evaluation_outcome"] == "correct") != success:
            raise ValueError("Trace/native outcome mismatch")
        return success


def validate_local_resume(result, task, start, validator):
    """Recheck saved attempts without another model or website execution."""
    from .stage1 import best_successful
    if result.get("local_reward_contract_sha256") != validator.contract_sha256:
        raise ValueError("Cached result belongs to a different local reward contract")
    require_metric(result)
    attempts = result["attempts"]
    for attempt in attempts:
        trace = read_pinned_json({
            "path": attempt["validation"]["trajectory_path"],
            "sha256": attempt["validation"]["trajectory_sha256"],
        })
        if validator(trace, task, start, attempt["skill"]) != attempt["success"]:
            raise ValueError("Cached local outcome changed")
        require_metric(attempt)
        if (type(attempt["steps"]) is not int or type(attempt["generation_rounds"]) is not int
                or selection_steps(trace) != attempt["steps"] or trace["rounds"] != attempt["generation_rounds"]):
            raise ValueError("Cached local step count changed")
    best = best_successful(attempts)
    if result["status"] != ("accepted" if best else "rejected"):
        raise ValueError("Cached local selection changed")
    if best is not None:
        record = result["verified_record"]
        require_metric(record["metadata"])
        if (record["metadata"]["verification_steps"] != best["steps"] or
                record["metadata"]["verification_generation_rounds"] != best["generation_rounds"]):
            raise ValueError("Cached selected execution metric changed")
        if record["target"] != best["skill"] or record["metadata"]["validation"] != best["validation"]:
            raise ValueError("Cached local target differs from the best verified attempt")
        if record["metadata"]["training_data"] is not False or record["metadata"]["output_purpose"] != "engineering_pilot":
            raise ValueError("Cached pilot cannot become formal training data")
    return result
