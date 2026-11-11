"""Existing-only namespace opening uses original live gates and never creates.

Actual installed worker/cgroup/store checks. Faults modify only this synthetic
test namespace, restore its original fixture bytes, and grant no task or replay.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
import os
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.storage.registered_protocol import (
    RegisteredStorageCommand,
    encode_registered_command,
    decode_registered_command,
)
from lab_generate_skill.adapters.storage.registered_transport import (
    RegisteredStorageFailure,
)
from lab_generate_skill.bootstrap.owner_metadata_store import owner_metadata_store
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.storage_scope import OwnerMetadataStorageScope
from lab_generate_skill.domain.errors import OperationStopped, InvalidTransition
from lab_generate_skill.runtime.lifecycle import OperationGuards
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from registered_storage_fixtures import request, roots
from test_linux_cgroups import actual_slurm_execution
from test_resource_journal import NoCancellation
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "old_version",
        "create_new_version",
        "exchange_new_version",
        "io",
        "revision",
        "payload",
    ],
)
def test_existing_only_operation_is_explicit_and_cannot_disguise_exchange(
    tmp_path: Path, fault: str
) -> None:
    command = request(tmp_path, create=True)
    changes: dict[str, Any] = {
        "schema_version": "registered-storage-command/4",
        "action": "open_existing",
    }
    if fault == "old_version":
        changes["schema_version"] = "registered-storage-command/3"
    elif fault == "create_new_version":
        changes["action"] = "create"
    elif fault == "exchange_new_version":
        command = request(tmp_path)
        changes["action"] = "exchange"
    elif fault == "io":
        changes["io"] = request(tmp_path).io
    elif fault == "revision":
        changes["expected_revision"] = 0
    if fault == "none":
        selected = RegisteredStorageCommand.model_validate(
            command.model_copy(update=changes)
        )
        assert decode_registered_command(encode_registered_command(selected)) == (
            selected,
            b"",
        )
    else:
        with pytest.raises(ValueError):
            selected = RegisteredStorageCommand.model_validate(
                command.model_copy(update=changes)
            )
            encode_registered_command(
                selected, b"not-a-read" if fault == "payload" else b""
            )
    assert list(tmp_path.iterdir()) == []


@pytest.fixture(scope="module")
def namespace(
    tmp_path_factory: pytest.TempPathFactory, installed_sources: InstalledFixture
) -> Iterator[Any]:
    execution, _ = actual_slurm_execution()
    root = tmp_path_factory.mktemp("original-existing-namespace")
    roots(root)
    command = request(root, create=True, installation=installed_sources)
    owner = command.binding.owner.model_copy(
        update={
            "run_id": "existing-source-" + execution.job_id,
            "job_id": execution.job_id,
        }
    )
    binding = command.binding.model_copy(
        update={"scope": "run", "source_task_id": None, "owner": owner}
    )
    workspace = Path(os.path.commonpath([str(root), str(installed_sources.workspace)]))
    scope = OwnerMetadataStorageScope(
        binding=binding,
        config=command.config,
        writer=current_process_identity(),
        execution=execution,
        workspace_root=str(workspace),
    )
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    op = OperationContext(
        operation_id="existing-source-namespace",
        run_id=owner.run_id,
        owner_id=owner.owner_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=280),
    )

    def bound() -> Any:
        return owner_metadata_store(
            scope,
            op,
            clock,
            controls,
            controls.bind(op),
            max_io_seconds=30,
            cleanup_seconds=15,
        )

    original = bound()
    original.store.initialize(controls.bind(op))
    raw = b'{"original_source_fact":true}'
    ref = original.store.put(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="source-test-fact/1",
            visibility="private",
            producer="existing-source-test",
        ),
        controls.bind(op),
    )
    try:
        yield SimpleNamespace(
            root=root,
            scope=scope,
            op=op,
            controls=controls,
            bound=bound,
            ref=ref,
            raw=raw,
        )
    finally:
        original.admission.stop_new_io()


@pytest.mark.parametrize(
    "fault", ["none", "missing", "corrupt", "unknown", "empty", "denied", "cancel"]
)
def test_actual_installed_existing_open_preserves_history_and_never_creates(
    namespace: Any, fault: str
) -> None:
    c = namespace
    selected = c.bound()
    snapshot = Path(c.scope.config.session_root) / (
        c.scope.binding.namespace_key + ".evidence-session.json"
    )
    raw = snapshot.read_bytes()
    if fault == "missing":
        snapshot.unlink()
    elif fault == "corrupt":
        snapshot.write_bytes(b"{broken")
    elif fault in {"unknown", "empty"}:
        parsed = EvidenceSessionSnapshot.model_validate_json(raw)
        entries = (
            ()
            if fault == "empty"
            else (
                *parsed.entries[:-1],
                parsed.entries[-1].model_copy(
                    update={"outcome": None, "resolutions": ()}
                ),
            )
        )
        changed = (
            parsed.model_copy(update={"entries": entries}).model_dump_json().encode()
        )
        check = EvidenceSessionSnapshot.model_validate_json(changed)
        assert not check.entries if fault == "empty" else not check.entries[-1].reusable
        snapshot.write_bytes(changed)
    before = {
        str(p.relative_to(c.root)): p.read_bytes()
        for p in c.root.rglob("*")
        if p.is_file()
    }
    control: Any = c.controls.bind(c.op)
    if fault == "denied":
        selected.admission.stop_new_io()
    elif fault == "cancel":

        class Stop:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "existing-open")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        control = Stop()
    try:
        if fault == "none":
            actual = selected.store.open_existing(control)
            assert (
                actual.binding == c.scope.binding
                and actual.entries
                and actual.entries[-1].reusable
            )
            assert selected.store.state == "ready"
            assert before == {
                str(p.relative_to(c.root)): p.read_bytes()
                for p in c.root.rglob("*")
                if p.is_file()
            }
            # This is the first actual post-open exchange; it must keep original
            # revision/authority and retrieve the original complete CAS object.
            assert selected.store.read(c.ref, control) == c.raw
        else:
            expected = (
                OperationStopped
                if fault == "cancel"
                else (
                    InvalidTransition if fault == "denied" else RegisteredStorageFailure
                )
            )
            with pytest.raises(expected) as caught:
                selected.store.open_existing(control)
            if isinstance(caught.value, RegisteredStorageFailure):
                assert (
                    caught.value.phase == "worker" and caught.value.result is not None
                )
                assert (
                    caught.value.result.reply.schema_version
                    == "registered-storage-reply/4"
                )
                assert caught.value.result.reply.phase == "existing_namespace_read"
            elif isinstance(caught.value, OperationStopped):
                assert caught.value.reason_code == "CANCELLED"
            assert selected.store.state != "ready"
            assert before == {
                str(p.relative_to(c.root)): p.read_bytes()
                for p in c.root.rglob("*")
                if p.is_file()
            }
            if fault == "missing":
                assert not snapshot.exists()
    finally:
        selected.admission.stop_new_io()
        if fault in {"missing", "corrupt", "unknown", "empty"}:
            snapshot.write_bytes(raw)
