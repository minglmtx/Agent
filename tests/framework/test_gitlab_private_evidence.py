"""Transport/schema only: synthetic large JSON, explicit fixture admission."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.native_private_json import GITLAB_PRIVATE_JSON
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    EvidenceIntegrityError,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.gitlab_private_evidence import (
    GitlabPrivateEvidence,
)
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceContext
from evidence_control_fixtures import EvidenceFixtureStore
from evidence_session_fixtures import capacity
from site_worker_fixtures import configuration, operation
from test_gitlab_ssh_key_inputs import public_task, FIXTURE, reference
from lab_generate_skill.bootstrap.gitlab_ssh_key import load_ssh_key_inputs
from test_slurm_commands import guard
from generator_worker_fixtures import unit_guard
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)


class Admission:
    denied = False

    def __init__(
        self, plan: SitePrivateEvidencePlan, context: SitePrivateEvidenceContext
    ) -> None:
        self.plan, self.context = plan, context
        self.calls: list[str] = []

    def authorize(
        self,
        plan: SitePrivateEvidencePlan,
        context: SitePrivateEvidenceContext,
        request: SiteTaskRequest,
        phase: Literal["publish", "read"],
        control: OperationControl,
    ) -> None:
        assert plan == self.plan and context == self.context
        control.checkpoint()
        self.calls.append(phase)
        if self.denied:
            raise PermissionError("Explicit fixture permission denied")


@dataclass
class Case:
    transport: GitlabPrivateEvidence
    store: EvidenceFixtureStore
    admission: Admission
    request: SiteTaskRequest


@pytest.fixture
def c(tmp_path: Path) -> Case:
    base = configuration()
    files = SiteFilesPlan.model_validate(
        {
            **base.files.model_dump(),
            "workspace_root": str(tmp_path),
            "source_path": str(tmp_path / "admin.sif"),
        }
    )
    config = EvidenceStorageConfig(
        storage_id="native-site-store",
        evidence_root=str(tmp_path / "data"),
        session_root=str(tmp_path / "sessions"),
        max_object_bytes=64 * 1024 * 1024,
        capacity=capacity(),
        installation=base.installation,
    )
    plan = SitePrivateEvidencePlan(
        profile=GITLAB_PRIVATE_JSON,
        resource_journal_root=str(tmp_path / "original-site-journal"),
        binding=EvidenceSessionBinding(
            storage_id=config.storage_id,
            scope="run",
            source_task_id=None,
            session_id="site-original-session",
            owner=base.token.owner,
            release_id=base.installation.manifest.release_id,
            storage_config_sha256=config.sha256,
        ),
        config=config,
    )
    context = SitePrivateEvidenceContext(
        configuration_sha256="a" * 64,
        token=base.token,
        instance=SiteInstanceStarted(
            files=files, endpoint="http://127.0.0.1:18080/", ports=(18080, 18081)
        ),
        owner_guard=unit_guard(current_process_identity(), guard(10)),
    )
    (tmp_path / "data").mkdir(mode=0o700)
    (tmp_path / "sessions").mkdir(mode=0o700)
    store = EvidenceFixtureStore(tmp_path / "data")
    admission = Admission(plan, context)
    transport = GitlabPrivateEvidence(plan, context, store, admission)
    native = FIXTURE.read_bytes()
    inputs = load_ssh_key_inputs(native, reference(native), public_task())
    request = SiteTaskRequest(
        task=inputs.public_task.identity,
        binding_ref=reference(b"{}", content_schema="task-binding/1"),
        operation=operation(base).model_copy(
            update={
                "attempt_id": "gitlab-attempt",
                "operation_id": "gitlab-private-capture",
            }
        ),
        action="inspect",
        snapshot_ref=reference(b"{}", content_schema="gitlab-full-recovery/1"),
        private_input=inputs.private_spec.model_dump_json(),
    )
    return Case(transport, store, admission, request)


def test_complete_large_json_crosses_cas_without_raising_rpc_limits(c: Case) -> None:
    from lab_generate_skill.adapters.sites.worker_protocol import MAX_PACKET

    size = 17_606_758
    raw = b'{"synthetic_padding":"' + b"x" * (size - 24) + b'"}'
    assert len(raw) > MAX_PACKET
    with pytest.raises(ValidationError):
        SiteTaskResult(request_sha256=c.request.digest, private_result=raw.decode())
    result = c.transport.publish(c.request, raw, control=guard(30))
    assert result.payload_ref.size_bytes == len(raw)
    assert c.transport.read(c.request, result, control=guard(30)) == raw
    assert len(result.model_dump_json().encode()) < 8192
    assert (
        SiteTaskResult(
            request_sha256=c.request.digest, private_result=result.model_dump_json()
        ).request_sha256
        == c.request.digest
    )
    assert c.admission.calls == ["publish", "read"]
    assert result.context.owner_guard == c.transport.context.owner_guard
    with pytest.raises(InvalidTransition):
        c.transport.publish(c.request, raw, control=guard(5))


@pytest.mark.parametrize(
    "raw", [b"", b"[]", b"null", b'{"a":1,"a":2}', b'{"a":NaN}', b"\xff"]
)
def test_invalid_json_has_no_storage_effect(c: Case, raw: bytes) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        c.transport.publish(c.request, raw, control=guard(5))
    assert not c.admission.calls and not c.transport.attempted
    assert not list((Path(c.transport.plan.config.evidence_root) / "blobs").iterdir())


@pytest.mark.parametrize(
    "mode", ["denied", "foreign_run", "foreign_allocation", "foreign_site"]
)
def test_admission_and_scope_precede_storage(c: Case, mode: str) -> None:
    request = c.request
    if mode == "denied":
        c.admission.denied = True
    elif mode in ("foreign_run", "foreign_allocation"):
        field = "run_id" if mode == "foreign_run" else "allocation_id"
        request = request.model_copy(
            update={"operation": request.operation.model_copy(update={field: "other"})}
        )
    else:
        request = request.model_copy(
            update={"task": request.task.model_copy(update={"site": "shopping"})}
        )
    with pytest.raises((PermissionError, OwnershipConflict)):
        c.transport.publish(request, b"{}", control=guard(5))
    assert not c.transport.attempted and not c.transport.quarantined


@pytest.mark.parametrize("fault", ["lost_ack", "wrong_ref"])
def test_unknown_publication_retains_candidate_and_never_retries(
    c: Case, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    original = c.store.put
    calls = 0
    primary = OSError("Original storage acknowledgement unavailable")

    def put(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        nonlocal calls
        calls += 1
        actual = original(raw, metadata, control=control)
        if fault == "lost_ack":
            raise primary
        return actual.model_copy(update={"producer": "foreign"})

    monkeypatch.setattr(c.store, "put", put)
    with pytest.raises((OSError, EvidenceIntegrityError)) as caught:
        c.transport.publish(c.request, b'{"complete":true}', control=guard(5))
    if fault == "lost_ack":
        assert caught.value is primary
    candidate = c.transport.last_candidate
    assert candidate is not None and c.transport.quarantined
    assert c.store.read(candidate.payload_ref, control=guard(5)) == b'{"complete":true}'
    with pytest.raises(InvalidTransition):
        c.transport.publish(c.request, b"{}", control=guard(5))
    with pytest.raises(InvalidTransition):
        c.transport.read(c.request, candidate, control=guard(5))
    assert calls == 1


@pytest.mark.parametrize(
    "fault",
    ["request", "worker", "configuration", "instance", "public", "schema", "corrupt"],
)
def test_foreign_or_corrupt_descriptor_is_not_native_fact(
    c: Case, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    result = c.transport.publish(c.request, b"{}", control=guard(5))
    if fault == "request":
        result = result.model_copy(update={"request_sha256": "f" * 64})
    elif fault in ("worker", "configuration", "instance"):
        context = result.context
        if fault == "worker":
            context = context.model_copy(
                update={
                    "owner_guard": context.owner_guard.model_copy(
                        update={
                            "worker": context.owner_guard.worker.model_copy(
                                update={
                                    "start_ticks": context.owner_guard.worker.start_ticks
                                    + 1
                                }
                            )
                        }
                    )
                }
            )
        elif fault == "configuration":
            context = context.model_copy(update={"configuration_sha256": "f" * 64})
        else:
            context = context.model_copy(
                update={
                    "instance": context.instance.model_copy(
                        update={
                            "endpoint": "http://127.0.0.1:18082/",
                            "ports": (18082, 18081),
                        }
                    )
                }
            )
        result = result.model_copy(update={"context": context})
    elif fault in ("public", "schema"):
        result = result.model_copy(
            update={
                "payload_ref": result.payload_ref.model_copy(
                    update=(
                        {"visibility": "public"}
                        if fault == "public"
                        else {"content_schema": "foreign/1"}
                    )
                )
            }
        )
    else:
        monkeypatch.setattr(c.store, "read", lambda *args, **kwargs: b"changed")
    with pytest.raises((OwnershipConflict, EvidenceIntegrityError)):
        c.transport.read(c.request, result, control=guard(5))


@pytest.mark.parametrize(
    "fault",
    [
        "source_claim",
        "config_digest",
        "release",
        "node_state",
        "foreign_owner",
        "foreign_installation",
    ],
)
def test_plan_rejects_scope_substitution_and_resettable_evidence_root(
    c: Case, fault: str
) -> None:
    plan = c.transport.plan
    data = plan.model_dump(mode="json")
    if fault == "source_claim":
        data["binding"].update(scope="source", source_task_id="invented-claim")
    elif fault in ("config_digest", "release"):
        data["binding"][
            "storage_config_sha256" if fault == "config_digest" else "release_id"
        ] = ("f" * 64)
    elif fault == "node_state":
        data["config"]["evidence_root"] = (
            c.transport.context.instance.files.state_root + "/evidence"
        )
        data["binding"]["storage_config_sha256"] = (
            EvidenceStorageConfig.model_validate_json(json.dumps(data["config"])).sha256
        )
    elif fault == "foreign_owner":
        data["binding"]["owner"]["owner_id"] = "other"
    else:
        data["config"]["installation"]["python_executable"] = "/different/python"
        data["binding"]["storage_config_sha256"] = (
            EvidenceStorageConfig.model_validate_json(json.dumps(data["config"])).sha256
        )
    if fault in ("source_claim", "config_digest", "release"):
        with pytest.raises(ValidationError):
            SitePrivateEvidencePlan.model_validate_json(json.dumps(data))
    else:
        with pytest.raises(OwnershipConflict):
            SitePrivateEvidencePlan.model_validate_json(json.dumps(data)).check_site(
                c.transport.context.token,
                c.transport.context.instance.files,
                plan.config.installation,
            )


@pytest.mark.parametrize("when", ["before_write", "after_write"])
def test_cancellation_preserves_original_write_boundary(
    c: Case, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    from lab_generate_skill.domain.errors import OperationStopped

    class Control:
        cancelled = when == "before_write"

        def checkpoint(self) -> float:
            if self.cancelled:
                raise OperationStopped("cancelled", c.request.operation.operation_id)
            return 10.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    control = Control()
    original = c.store.put
    writes = 0

    def put(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        nonlocal writes
        result = original(raw, metadata, control=control)
        writes += 1
        assert isinstance(control, Control)
        control.cancelled = True
        return result

    monkeypatch.setattr(c.store, "put", put)
    with pytest.raises(OperationStopped):
        c.transport.publish(c.request, b"{}", control=control)
    if when == "before_write":
        assert writes == 0 and not c.transport.attempted and not c.transport.quarantined
    else:
        assert (
            writes == 1
            and c.transport.last_candidate is not None
            and c.transport.quarantined
        )
        assert (
            c.store.read(c.transport.last_candidate.payload_ref, control=guard(5))
            == b"{}"
        )
        with pytest.raises(InvalidTransition):
            c.transport.publish(c.request, b"{}", control=guard(5))
