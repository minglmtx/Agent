"""Recorded real bytes plus malformed variants; no runtime admission claim."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.slurm.allocation_codec import (
    CONTROLLER_MAX_BYTES,
    parse_controller_allocation,
)
from lab_generate_skill.adapters.slurm.gpu_devices import (
    GPU_MAX_BYTES,
    parse_gpu_device,
)
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import (
    SlurmControllerAllocation,
    SlurmGpuDevice,
)

FIXTURES = Path(__file__).parent / "fixtures" / "slurm-allocation-4751471"
FIXTURE_HASHES = {
    "controller.json": "d94ab56a8f15d7845970a5486b242a9d43e971fa4d79d8b591e638b54a218df6",
    "gpu.xml": "f21ff4f6122826e34090b872c0c146ea4d188170fa2798e09b89930698782965",
}


def original_identity(**changes: object) -> SlurmExecutionIdentity:
    # DBIndex is deliberately synthetic: these controller bytes cannot prove it.
    values: dict[str, object] = dict(
        cluster="alex",
        job_id="4751471",
        raw_job_id="4751471",
        database_index="999",
        uid=215829,
        submitted_at_epoch=1793029433,
        started_at_epoch=1793029457,
        restart_count=0,
    )
    values.update(changes)
    return SlurmExecutionIdentity.model_validate(values)


def controller() -> dict[str, Any]:
    data: object = json.loads((FIXTURES / "controller.json").read_bytes())
    assert isinstance(data, dict)
    return data


def decode(value: dict[str, Any]) -> object:
    return parse_controller_allocation(
        json.dumps(value).encode(), original_identity(), "a0125"
    )


def test_recorded_bytes_and_repeat_are_stable() -> None:
    provenance = json.loads((FIXTURES / "provenance.json").read_bytes())
    before = {
        name: (FIXTURES / name).read_bytes() for name in ("controller.json", "gpu.xml")
    }
    for name, raw in before.items():
        assert hashlib.sha256(raw).hexdigest() == provenance["files"][name]["sha256"]
        assert hashlib.sha256(raw).hexdigest() == FIXTURE_HASHES[name]
        assert len(raw) == provenance["files"][name]["size_bytes"]
    for _ in range(2):
        allocation = parse_controller_allocation(
            before["controller.json"], original_identity(), "a0125"
        )
        device = parse_gpu_device(before["gpu.xml"])
        assert allocation.job_id == "4751471"
        assert allocation.node_id == "a0125"
        assert allocation.gpu_type == "a40"
        assert allocation.gpu_index == device.minor_number == 2
        assert device.uuid == "GPU-92ed713b-35f3-9228-5fc6-b2a046615a81"
        assert device.pci_bus_id == "00000000:25:00.0"
        assert device.product_name == "NVIDIA A40"
        assert "database_index" not in SlurmControllerAllocation.model_fields
    assert before == {name: (FIXTURES / name).read_bytes() for name in before}


@pytest.mark.parametrize(
    "field,value",
    [
        ("cluster", "foreign"),
        ("job_id", 4751472),
        ("job_id", "4751471"),
        ("user_id", True),
        ("user_id", 1000),
        ("restart_cnt", 1),
        ("job_state", ["COMPLETED"]),
        ("job_state", ["RUNNING", "COMPLETING"]),
        ("nodes", "a0125,a0126"),
        ("batch_host", "a0126"),
        ("submit_time", {"set": True, "infinite": False, "number": 1793029434}),
        ("start_time", {"set": False, "infinite": False, "number": 1793029457}),
        ("start_time", {"set": True, "infinite": True, "number": 1793029457}),
        ("start_time", {"set": 1, "infinite": False, "number": 1793029457}),
        ("start_time", {"set": True, "infinite": False, "number": 1793029457.0}),
        ("array_job_id", {"set": True, "infinite": False, "number": 123}),
        ("array_task_id", {"set": True, "infinite": False, "number": 0}),
        ("het_job_id", {"set": True, "infinite": False, "number": 123}),
        ("gres_detail", []),
        ("gres_detail", ["gpu:a40:2(IDX:2-3)"]),
        ("gres_detail", ["gpu:a40:1(IDX:02)"]),
        ("gres_detail", ["gpu:a40:1(IDX:2)", "gpu:a40:1(IDX:3)"]),
        ("gres_detail", ["gpu:a40:1(IDX:1048576)"]),
        ("gres_detail", [None]),
        ("job_resources", None),
    ],
)
def test_wrong_job_fact_rejected(field: str, value: object) -> None:
    data = controller()
    data["jobs"][0][field] = value
    with pytest.raises(ValueError):
        decode(data)


@pytest.mark.parametrize(
    "field",
    [
        "cluster",
        "job_id",
        "user_id",
        "restart_cnt",
        "submit_time",
        "start_time",
        "job_state",
        "array_job_id",
        "array_task_id",
        "het_job_id",
        "nodes",
        "batch_host",
        "job_resources",
        "gres_detail",
    ],
)
def test_missing_required_job_fact_rejected(field: str) -> None:
    data = controller()
    del data["jobs"][0][field]
    with pytest.raises(ValueError):
        decode(data)


@pytest.mark.parametrize(
    "path,value",
    [
        (("errors",), [{}]),
        (("warnings",), ["truncated"]),
        (("jobs",), []),
        (("jobs",), [None]),
        (("jobs",), {}),
        (("meta", "plugin", "data_parser"), "data_parser/v0.0.43"),
        (("meta", "slurm", "cluster"), "elsewhere"),
        (("jobs", 0, "job_resources", "nodes", "count"), True),
        (("jobs", 0, "job_resources", "nodes", "count"), 2),
        (("jobs", 0, "job_resources", "nodes", "list"), "a0126"),
        (("jobs", 0, "job_resources", "nodes", "allocation"), []),
        (("jobs", 0, "job_resources", "nodes", "allocation", 0, "name"), "a0126"),
        (("jobs", 0, "job_resources", "nodes", "allocation", 0, "index"), True),
    ],
)
def test_ambiguous_controller_context_rejected(
    path: tuple[str | int, ...], value: object
) -> None:
    data = controller()
    target: Any = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        decode(data)


def test_multiple_jobs_and_wrong_writer_rejected() -> None:
    data = controller()
    data["jobs"] *= 2
    with pytest.raises(ValueError):
        decode(data)
    with pytest.raises(ValueError):
        parse_controller_allocation(
            (FIXTURES / "controller.json").read_bytes(), original_identity(), "a0126"
        )
    with pytest.raises(ValueError, match="Array"):
        parse_controller_allocation(
            (FIXTURES / "controller.json").read_bytes(),
            original_identity(job_id="4000000_1"),
            "a0125",
        )


@pytest.mark.parametrize(
    "raw", [b"", b"[]", b"null", b"{", b"\xff", b'{"jobs":[],"jobs":[]}', b'{"x":NaN}']
)
def test_invalid_json(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_controller_allocation(raw, original_identity(), "a0125")


def test_extreme_json_nesting_is_a_format_error() -> None:
    raw = b'{"extra":' + b"[" * 10000 + b"0" + b"]" * 10000 + b"}"
    with pytest.raises(ValueError, match="nesting") as caught:
        parse_controller_allocation(raw, original_identity(), "a0125")
    assert isinstance(caught.value.__cause__, RecursionError)


@pytest.mark.parametrize("name", ["controller.json", "gpu.xml"])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_byte_bounds(name: str, offset: int) -> None:
    raw = (FIXTURES / name).read_bytes()
    bound = CONTROLLER_MAX_BYTES if name == "controller.json" else GPU_MAX_BYTES
    raw += b" " * (bound + offset - len(raw))

    def run() -> object:
        return (
            parse_controller_allocation(raw, original_identity(), "a0125")
            if name == "controller.json"
            else parse_gpu_device(raw)
        )

    if offset > 0:
        with pytest.raises(ValueError, match="bounds"):
            run()
    else:
        assert run() is not None


@pytest.mark.parametrize("bad", [None, "", 1, True, bytearray(b"{}")])
def test_exact_input_type(bad: Any) -> None:
    with pytest.raises(TypeError):
        parse_controller_allocation(bad, original_identity(), "a0125")
    with pytest.raises(TypeError):
        parse_gpu_device(bad)


@pytest.mark.parametrize(
    "old,new",
    [
        ("<attached_gpus>1</attached_gpus>", "<attached_gpus>2</attached_gpus>"),
        ("<attached_gpus>1</attached_gpus>", ""),
        ("<minor_number>2</minor_number>", "<minor_number>02</minor_number>"),
        ("<minor_number>2</minor_number>", "<minor_number>-1</minor_number>"),
        ("<minor_number>2</minor_number>", "<minor_number>1048576</minor_number>"),
        ("<minor_number>2</minor_number>", "<minor_number><x>2</x></minor_number>"),
        (
            "<minor_number>2</minor_number>",
            "<minor_number>2</minor_number><minor_number>2</minor_number>",
        ),
        ("<current_mig>N/A</current_mig>", "<current_mig>Enabled</current_mig>"),
        ("<pending_mig>N/A</pending_mig>", "<pending_mig>Enabled</pending_mig>"),
        ("<mig_devices>", "<mig_devices><device>1</device>"),
        ('gpu id="00000000:25:00.0"', 'gpu id="00000000:26:00.0"'),
        ("<uuid>GPU-", "<uuid>MIG-"),
        ("<uuid>", '<uuid data="x">'),
        ("<nvidia_smi_log>", "<unexpected>"),
        ("</nvidia_smi_log>", "<gpu/></nvidia_smi_log>"),
        (
            '<!DOCTYPE nvidia_smi_log SYSTEM "nvsmi_device_v13.dtd">',
            '<!DOCTYPE nvidia_smi_log [<!ENTITY a "x">]>',
        ),
        (
            '<!DOCTYPE nvidia_smi_log SYSTEM "nvsmi_device_v13.dtd">',
            '<!DOCTYPE nvidia_smi_log SYSTEM "file:///etc/passwd">',
        ),
    ],
)
def test_gpu_malformed_or_unsupported(old: str, new: str) -> None:
    raw = (FIXTURES / "gpu.xml").read_text()
    assert old in raw
    with pytest.raises(ValueError):
        parse_gpu_device(raw.replace(old, new, 1).encode())


@pytest.mark.parametrize("raw", [b"", b"\xff", b"<gpu/>", b"<", b"<nvidia_smi_log/>"])
def test_invalid_xml(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_gpu_device(raw)


def test_disabled_mig_and_no_doctype_are_supported() -> None:
    raw = (FIXTURES / "gpu.xml").read_text()
    raw = raw.replace('<!DOCTYPE nvidia_smi_log SYSTEM "nvsmi_device_v13.dtd">', "")
    raw = raw.replace(
        "<current_mig>N/A</current_mig>", "<current_mig>Disabled</current_mig>"
    )
    raw = raw.replace(
        "<pending_mig>N/A</pending_mig>", "<pending_mig>Disabled</pending_mig>"
    )
    assert parse_gpu_device(raw.encode()).minor_number == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("uuid", "GPU-invalid"),
        ("minor_number", True),
        ("minor_number", -1),
        ("pci_bus_id", "00000000:25:20.0"),
        ("pci_bus_id", "00000000:25:00.8"),
        ("product_name", ""),
        ("product_name", "NVIDIA\nA40"),
    ],
)
def test_domain_rejects_invalid_device_fields(field: str, value: object) -> None:
    data = parse_gpu_device((FIXTURES / "gpu.xml").read_bytes()).model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        SlurmGpuDevice.model_validate(data)
