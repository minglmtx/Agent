"""Recorded step JSON/text, exact warnings and independent identity/resource checks."""

import hashlib
import json
from typing import Any

import pytest

from lab_generate_skill.adapters.slurm.step_codec import (
    parse_step_json,
    check_step_absent,
    STEP_MAX_BYTES,
)
from lab_generate_skill.adapters.slurm.step_text import check_step_text
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep
from slurm_step_fixtures import FIXTURES, target, recorded, encoded, epoch_text


def test_exact_recorded_facts_and_repeated_read() -> None:
    provenance = json.loads((FIXTURES / "provenance.json").read_bytes())
    for name, identity in provenance["files"].items():
        raw = (FIXTURES / name).read_bytes()
        assert len(raw) == identity["size_bytes"]
        assert hashlib.sha256(raw).hexdigest() == identity["sha256"]
    raw, text = (FIXTURES / "running.json").read_bytes(), (
        FIXTURES / "running.txt"
    ).read_bytes()
    first = parse_step_json(raw, target())
    assert parse_step_json(raw, target()) == first
    assert first.started_at_epoch == 1793034325 and first.gpu_type == "a100"
    assert first.memory == "120000M"
    assert SlurmControllerStep.model_validate_json(first.model_dump_json()) == first
    with pytest.raises(ValueError, match="epoch"):
        check_step_text(text, first)
    check_step_text(epoch_text(), first)
    check_step_text(text.replace(b"2026-10-26T18:05:25", b"1793034325"), first)
    check_step_absent((FIXTURES / "absent.json").read_bytes(), target())


@pytest.mark.parametrize(
    "path,value",
    [
        (("errors",), [{"error": "denied"}]),
        (("warnings",), []),
        (("warnings",), [{"description": "other", "source": ""}]),
        (("meta", "plugin", "data_parser"), "new"),
        (("meta", "slurm", "cluster"), "other"),
        (("steps",), []),
        (("steps",), {}),
        (("steps",), [{}, {}]),
        (("steps", 0, "array", "job_id"), True),
        (("steps", 0, "array", "job_id"), 1),
        (("steps", 0, "array", "task_id"), None),
        (("steps", 0, "array", "task_id"), 0),
        (("steps", 0, "array", "task_id"), 4294967295),
        (("steps", 0, "id"), "4752096.1"),
        (("steps", 0, "id"), "4752097.0"),
        (("steps", 0, "cluster"), "other"),
        (("steps", 0, "name"), "other"),
        (("steps", 0, "nodes"), "a0535,a0121"),
        (("steps", 0, "state"), ["COMPLETED"]),
        (("steps", 0, "srun", "host"), "other"),
        (("steps", 0, "srun", "pid"), True),
        (("steps", 0, "srun", "pid"), 2949042),
        (("steps", 0, "srun", "pid"), "2949041"),
        (("steps", 0, "number_cpus"), True),
        (("steps", 0, "number_cpus"), 2),
        (("steps", 0, "number_tasks"), 0),
        (("steps", 0, "container"), "container"),
        (("steps", 0, "container_id"), "container"),
        (("steps", 0, "time", "start", "set"), False),
        (("steps", 0, "time", "start", "infinite"), True),
        (("steps", 0, "time", "start", "number"), True),
        (("steps", 0, "time", "start", "number"), 0),
        (("steps", 0, "time", "start", "number"), 1793034309),
        (("steps", 0, "tres", "per", "node"), "gres/gpu:2"),
        (("steps", 0, "tres", "per", "task"), "cpu=2,cpu:2"),
        (("steps", 0, "tres", "allocation"), "cpu=1,gres/gpu=1,node=1,mem=120000M"),
        (
            ("steps", 0, "tres", "allocation"),
            "cpu=1,cpu=1,gres/gpu:a100=1,gres/gpu=1,mem=120000M,node=1",
        ),
        (
            ("steps", 0, "tres", "allocation"),
            "cpu=1,gres/gpu:a100=2,gres/gpu=2,mem=120000M,node=1",
        ),
        (
            ("steps", 0, "tres", "allocation"),
            "cpu=1,gres/gpu:a100=1,gres/gpu=1,mem=0,node=1",
        ),
        (("steps", 0, "tres", "allocation"), None),
    ],
)
def test_wrong_json_fields(path: tuple[Any, ...], value: Any) -> None:
    data = recorded()
    cursor: Any = data
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    with pytest.raises(ValueError):
        parse_step_json(encoded(data), target())


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "array",
        "srun",
        "name",
        "time",
        "tres",
        "number_cpus",
        "nodes",
        "container",
        "state",
    ],
)
def test_missing_required_field(field: str) -> None:
    data = recorded()
    del data["steps"][0][field]
    with pytest.raises(ValueError):
        parse_step_json(encoded(data), target())


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{}",
        b"[]",
        b"null",
        b"\xff",
        b'{"steps":[],"steps":[]}',
        b'{"bad":NaN}',
        b"[" * 2000 + b"]" * 2000,
        b" " * (STEP_MAX_BYTES + 1),
    ],
)
def test_bad_json_bytes(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_step_json(raw, target())


@pytest.mark.parametrize("raw", [None, 0, False, "{}", {}, bytearray(b"{}")])
def test_wrong_bytes_type(raw: Any) -> None:
    with pytest.raises(TypeError):
        parse_step_json(raw, target())
    with pytest.raises(TypeError):
        check_step_text(raw, parse_step_json(encoded(recorded()), target()))


def test_exact_byte_limit() -> None:
    raw = encoded(recorded())
    padded = raw + b" " * (STEP_MAX_BYTES - len(raw))
    parsed = parse_step_json(padded, target())
    with pytest.raises(ValueError):
        parse_step_json(padded + b" ", target())
    text = epoch_text().rstrip(b"\n")
    text += b" " * (STEP_MAX_BYTES - len(text))
    check_step_text(text, parsed)
    with pytest.raises(ValueError):
        check_step_text(text + b" ", parsed)


@pytest.mark.parametrize(
    "old,new",
    [
        (b"UserId=215829", b"UserId=0"),
        (b"UserId=215829", b"UserId=r102bf10"),
        (b"StepId=4752096.0", b"StepId=4752096.00"),
        (b"CPUs=1", b"CPUs=2"),
        (b"Tasks=1", b"Tasks=true"),
        (b"Nodes=1", b"Nodes=2"),
        (b"NodeList=a0535", b"NodeList=a0536"),
        (b"Name=lab-generator-step-proof-4752096", b"Name=other"),
        (b"SrunHost:Pid=a0535:2949041", b"SrunHost:Pid=a0535:2949042"),
        (b"State=RUNNING", b"State=COMPLETED"),
        (b"1793034325", b"1793034326"),
        (b"gres/gpu:a100=1", b"gres/gpu:a40=1"),
        (b"mem=120000M", b"mem=120001M"),
        (b"TresPerNode=gres/gpu:1", b"TresPerNode=gres/gpu:2"),
    ],
)
def test_text_must_match_json_and_numeric_uid(old: bytes, new: bytes) -> None:
    raw = epoch_text()
    assert old in raw
    with pytest.raises(ValueError):
        check_step_text(
            raw.replace(old, new), parse_step_json(encoded(recorded()), target())
        )


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\n",
        b"bad",
        b"\xff",
        b"UserId=1 UserId=2",
        b"field=1\nfield=2\n",
        b"field=\x00",
        b"field=\t",
    ],
)
def test_bad_text_format(raw: bytes) -> None:
    with pytest.raises(ValueError):
        check_step_text(raw, parse_step_json(encoded(recorded()), target()))


@pytest.mark.parametrize(
    "field,value",
    [
        ("warnings", []),
        ("warnings", [{"description": "warning", "source": ""}]),
        ("steps", [{}]),
        ("errors", [{}]),
    ],
)
def test_absence_does_not_swallow_other_results(field: str, value: Any) -> None:
    data = json.loads((FIXTURES / "absent.json").read_bytes())
    data[field] = value
    with pytest.raises(ValueError):
        check_step_absent(encoded(data), target())


@pytest.mark.parametrize(
    "field,value",
    [
        ("step_name", ""),
        ("step_name", "--injected"),
        ("step_name", "name with space"),
        ("step_name", "x" * 129),
    ],
)
def test_invalid_target_names(field: str, value: Any) -> None:
    with pytest.raises(ValueError):
        SlurmStepTarget.model_validate(target().model_copy(update={field: value}))


def test_target_requires_distinct_launcher_and_original_worker() -> None:
    t = target()
    variants: list[dict[str, Any]] = [
        {"launcher": t.worker.writer},
        {"launcher": t.launcher.model_copy(update={"boot_id": "other"})},
        {"execution": t.execution.model_copy(update={"uid": 1})},
        {
            "worker": t.worker.model_copy(
                update={
                    "step_id": "batch",
                    "user_path": t.worker.user_path.replace("step_0", "step_batch"),
                }
            )
        },
    ]
    for changes in variants:
        with pytest.raises(ValueError):
            SlurmStepTarget.model_validate(t.model_copy(update=changes))
