"""Real installed metadata/Actor children and original cgroup close together.

The Actor fixture has explicit synthetic model/engineering admission. Runtime
evidence and journal IO use one actual managed store; no real model task runs.
"""

from datetime import timedelta
from pathlib import Path
import json
import pytest

from lab_generate_skill.adapters.models.actor_resource import registered_actor
from lab_generate_skill.adapters.storage.registered_transport import (
    RegisteredStorageFailure,
)
from lab_generate_skill.bootstrap.evidence_store import assemble_evidence_store
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_resource_fixtures import resource_case
from managed_store_fixtures import EngineeringAdmission
from registered_storage_fixtures import request
from test_slurm_commands import guard
from test_storage_unregistered_installed import ExpiredChildOperation
from test_actor_resource import inspect
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker


def test_unregistered_body_metadata_error_preserved_with_full_original_actor_close(
    tmp_path: Path,
    installed_sources: InstalledFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = resource_case(
        tmp_path, installed_sources.executable, installation=installed_sources
    )
    c.op = c.op.model_copy(update={"deadline": c.op.deadline + timedelta(seconds=600)})
    (tmp_path / "sessions").mkdir()
    declared = request(tmp_path, create=True, installation=installed_sources)
    config = declared.config.model_copy(
        update={
            "evidence_root": str(tmp_path / "evidence"),
            "max_object_bytes": 64 * 1024**2,
            "capacity": declared.config.capacity.model_copy(
                update={"max_exchanges": 1000, "max_bytes": 8 * 1024**2}
            ),
        }
    )
    binding = declared.binding.model_copy(
        update={"owner": c.spec.token.owner, "storage_config_sha256": config.sha256}
    )
    store = assemble_evidence_store(
        binding,
        config,
        str(installed_sources.executable),
        EngineeringAdmission(binding, config),
        c.clock,
        c.controls,
        guard(120),
        max_io_seconds=120,
        cleanup_seconds=120,
    )
    store.initialize(guard(120))

    # The optional-control facade is only fixture setup/readback convenience.
    # Every runtime read/write, including journal and closure-authority evidence,
    # delegates to the same installed managed store and original immutable CAS.
    def put(
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        assert exchange_id is None
        return store.put(data, metadata, control or guard(120))

    def read(reference: EvidenceRef, control: OperationControl | None = None) -> bytes:
        return store.read(reference, control or guard(120))

    monkeypatch.setattr(c.evidence, "put", put)
    monkeypatch.setattr(c.evidence, "read", read)
    failure: RegisteredStorageFailure | None = None
    with pytest.raises(RegisteredStorageFailure) as caught:
        with registered_actor(
            c.spec, c.op, cleanup_seconds=300, **c.dependencies()
        ) as engine:
            acquired = inspect(c)
            assert acquired.state == "acquired"
            with monkeypatch.context() as patch:
                patch.setattr(
                    store, "_operations", ExpiredChildOperation(store._operations)
                )
                try:
                    c.evidence.read(
                        acquired.events[-1].evidence[0], c.controls.bind(c.op)
                    )
                except RegisteredStorageFailure as error:
                    failure = error
                    assert store.state == "ready"
                    raise
    assert caught.value is failure and failure is not None
    record = inspect(c)
    assert [v.state for v in record.events] == [
        "registered",
        "acquiring",
        "acquired",
        "closing",
        "closed",
    ]
    closed = json.loads(c.evidence.read(record.events[-1].evidence[0]))
    assert closed["cleanup_errors"] == [] and closed["primary"] is not None
    assert closed["step_closed"] is not None and len(c.authority.workers) == 1
    assert len(c.authority.closed) == 1 and engine.capture.termination is not None
    assert engine.capture.termination.state == "reaped" and store.state == "ready"
