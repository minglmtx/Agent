"""Persist a terminal task judgment without losing the raw environment reward."""
def attach_terminal_evaluation(trace, judgment):
    status = judgment.get("status")
    reward = judgment.get("reward")
    if status not in ("success", "failure", "unknown"):
        raise ValueError("Unsupported terminal task status")
    if status == "unknown":
        if reward is not None:
            raise ValueError("Unscored task must not have a numeric reward")
    elif type(reward) not in (int, float) or reward != int(status == "success"):
        raise ValueError("Terminal task status and reward disagree")
    output = trace.get("task_output")
    if output is None:
        output = {}
    if not isinstance(output, dict):
        raise ValueError("Structured task output required")
    output.setdefault("openended_environment_reward", output.get("reward"))
    output["reward"] = reward
    trace["task_output"] = output
    trace["evaluation_outcome"] = {"success": "correct", "failure": "incorrect"}.get(status, "unknown")
    provenance = trace.setdefault("provenance", {})
    provenance.setdefault("environment_outcome_source", provenance.get("outcome_source"))
    provenance["outcome_source"] = "local_task_evaluator"
    provenance["local_evaluator_version"] = judgment.get("version")
    return trace
