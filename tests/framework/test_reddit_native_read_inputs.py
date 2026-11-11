"""Large private native-id artifacts with bounded selectors, no SQL or server."""

import json
from typing import Any
import os
from pathlib import Path
import pytest
from lab_generate_skill.adapters.sites.reddit_read_inputs import NativeReadInputs
from lab_generate_skill.domain.reddit_native_read_input import (
    BaselineIdsPayload,
    BaselineIdsUnconfirmed,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
)
from lab_generate_skill.sites.reddit.service_commands import container
from reddit_services_fixtures import spec
from test_browser_task_files_actual import frozen
from browsergym_fixtures import operation
from test_core_contracts import reference
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def request() -> SiteTaskRequest:
    session = frozen()
    op = operation(session, "snapshot").model_copy(
        update={
            "allocation_id": "site-allocation",
            "recovery_ref": reference(content_schema="recovery-plan/1"),
        }
    )
    return SiteTaskRequest(
        task=session.task.identity,
        binding_ref=reference(content_schema="task-binding/1"),
        operation=op,
        action="snapshot",
        snapshot_ref=None,
        private_input="{}",
    )


def test_large_range_artifact_readonly_binding_and_repeat_verification(
    node_path: Path,
) -> None:
    store = NativeReadInputs(str(node_path / "native-input"))
    req = request()
    ranges = tuple((2 * i + 1, 2 * i + 1) for i in range(2000))
    result = store.publish(req, ranges, 2000, guard(5))
    assert result.size_bytes > 8192 and len(result.model_dump_json().encode()) < 8192
    path = node_path / "native-input" / result.filename
    assert path.stat().st_mode & 0o777 == 0o400
    store.verify(result, guard(5))
    store.verify(result, guard(5))
    payload = BaselineIdsPayload.model_validate_json(path.read_bytes())
    assert (
        payload.ranges == ranges
        and payload.request_sha256 == req.digest
        and payload.task == req.task
    )
    assert str(node_path / "native-input") + ":/native-input:ro" in container(
        spec(node_path), native_input=True
    )
    assert str(node_path / "native-input") + ":/native-input:ro" not in container(
        spec(node_path)
    )
    with pytest.raises(InvalidTransition):
        store.publish(req, ranges, 2000, guard(5))
    fresh = NativeReadInputs(str(node_path / "native-input"))
    with pytest.raises(FileExistsError):
        fresh.publish(req, ranges, 2000, guard(5))
    assert path.read_bytes() == payload.model_dump_json().encode()


@pytest.mark.parametrize(
    "kind",
    [
        "bytes",
        "inode",
        "symlink",
        "hardlink",
        "permissions",
        "foreign-reference",
        "foreign-owner",
    ],
)
def test_unknown_changed_or_foreign_artifact_cannot_reach_native_read(
    node_path: Path, kind: str
) -> None:
    store = NativeReadInputs(str(node_path / "native-input"))
    result = store.publish(request(), ((1, 2),), 2, guard(5))
    path = node_path / "native-input" / result.filename
    if kind == "bytes":
        data = path.read_bytes()
        path.chmod(0o600)
        path.write_bytes(data[:-1] + b"!")
        path.chmod(0o400)
    elif kind == "inode":
        data = path.read_bytes()
        path.rename(path.with_suffix(".original"))
        path.write_bytes(data)
        path.chmod(0o400)
    elif kind == "symlink":
        path.unlink()
        path.symlink_to(node_path / "outside")
    elif kind == "hardlink":
        os.link(path, path.with_suffix(".link"))
    elif kind == "permissions":
        path.chmod(0o600)
    elif kind == "foreign-reference":
        result = result.model_copy(update={"sha256": "f" * 64})
    else:
        store.owner = (os.getpid() + 1, store.owner[1])
    with pytest.raises((EvidenceIntegrityError, OwnershipConflict, OSError)):
        store.verify(result, guard(5))


@pytest.mark.parametrize(
    "ranges,count",
    [
        (((1, 2),), 3),
        (((2, 1),), 2),
        (((1, 2), (2, 3)), 4),
        (((True, 2),), 2),
        (((0, 1),), 2),
        ((), 1),
    ],
)
def test_illegal_ranges_or_count_before_file_effect(
    node_path: Path, ranges: Any, count: int
) -> None:
    store = NativeReadInputs(str(node_path / "native-input"))
    with pytest.raises(ValueError):
        store.publish(request(), ranges, count, guard(5))
    assert not store.attempted and not (node_path / "native-input").exists()


def test_empty_native_ids_and_cancel_before_or_after_known_write(
    node_path: Path,
) -> None:
    store = NativeReadInputs(str(node_path / "native-input"))
    root = node_path / "native-input"

    class CancelBefore:
        def checkpoint(self) -> float:
            raise TimeoutError("cancelled")

        def wait(self, seconds: float) -> None:
            raise TimeoutError("cancelled")

    with pytest.raises(TimeoutError):
        store.publish(request(), (), 0, CancelBefore())
    assert not store.attempted and not root.exists()

    class CancelAfter:
        def checkpoint(self) -> float:
            if store.result is not None:
                raise TimeoutError("late cancellation")
            return 5

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(BaselineIdsUnconfirmed) as caught:
        store.publish(request(), (), 0, CancelAfter())
    result = caught.value.reference
    assert result == store.result
    store.verify(result, guard(5))
    with pytest.raises(InvalidTransition):
        store.publish(request(), (), 0, guard(5))


def test_partial_write_failure_is_not_adopted_or_rewritten(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = NativeReadInputs(str(node_path / "native-input"))
    req = request()
    original = os.write
    count = 0

    def write(fd: int, data: object) -> int:
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("original write failed")
        return original(fd, memoryview(data)[:1])  # type: ignore[arg-type]

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", write)
        with pytest.raises(OSError, match="original write failed"):
            store.publish(req, ((1, 2),), 2, guard(5))
    assert store.attempted and store.result is None and count == 2
    path = node_path / "native-input" / (req.digest + ".json")
    assert path.stat().st_size == 1
    with pytest.raises(InvalidTransition):
        store.publish(req, ((1, 2),), 2, guard(5))


@pytest.mark.parametrize(
    "value",
    [
        "/tmp/native-input",
        "/var/tmp/x/native-input",
        "/tmp/x/../native-input",
        "/tmp/x/other",
        "/tmp/x,n/native-input",
        None,
        True,
    ],
)
def test_invalid_input_root_is_inert(value: object) -> None:
    with pytest.raises(ValueError):
        NativeReadInputs(value)  # type: ignore[arg-type]
