"""Independent numeric UID and identity cross-check from bounded scontrol -o."""

from lab_generate_skill.domain.slurm_step import SlurmControllerStep
from .step_codec import STEP_MAX_BYTES


def check_step_text(raw: bytes, expected: SlurmControllerStep) -> None:
    expected = SlurmControllerStep.model_validate(expected)
    if type(raw) is not bytes:
        raise TypeError("Step text must be bytes")
    if not 0 < len(raw) <= STEP_MAX_BYTES:
        raise ValueError("Step text exceeds byte bounds")
    try:
        text = raw.decode("ascii")
    except UnicodeError as error:
        raise ValueError("Step text must be ASCII") from error
    if len(text.splitlines()) != 1 or any(ord(c) < 32 for c in text.rstrip("\n")):
        raise ValueError("Step text must contain one complete line")
    values: dict[str, str] = {}
    for item in text.strip().split(" "):
        if not item:
            continue
        key, sep, value = item.partition("=")
        if not sep or not key or key in values:
            raise ValueError("Malformed or duplicate step text field")
        values[key] = value
    target = expected.target
    required = {
        "StepId": target.step_key,
        "UserId": str(target.execution.uid),
        "Name": target.step_name,
        "State": "RUNNING",
        "NodeList": target.launcher.node_id,
        "Nodes": "1",
        "CPUs": "1",
        "Tasks": "1",
        "SrunHost:Pid": target.launcher.node_id + ":" + str(target.launcher.process_id),
        "TresPerStep": "cpu:1",
        "TresPerTask": "cpu=1,cpu:1",
    }
    if target.resources == "single_gpu":
        required["TresPerNode"] = "gres/gpu:1"
    elif "TresPerNode" in values:
        raise ValueError("CPU step must not declare a per-node GPU reservation")
    if any(values.get(key) != value for key, value in required.items()):
        raise ValueError(
            "Step text differs from original controller/UID/launcher facts"
        )
    # The query runner requests SLURM_TIME_FORMAT=%s. Unzoned historical dates
    # are ambiguous, even when this observer has TZ=UTC; never guess an offset.
    if values.get("StartTime") != str(expected.started_at_epoch):
        raise ValueError("Step text start time must match the JSON epoch exactly")
    expected_tres = {
        "cpu=1",
        "node=1",
        "mem=" + expected.memory,
    }
    if expected.gpu_type is not None:
        expected_tres.update({"gres/gpu=1", "gres/gpu:" + expected.gpu_type + "=1"})
    tres = values.get("TRES", "").split(",")
    if len(tres) != len(expected_tres) or set(tres) != expected_tres:
        raise ValueError("Step text resources differ from JSON")
