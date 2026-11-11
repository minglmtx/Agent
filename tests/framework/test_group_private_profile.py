"""Declared Group transport uses the existing controlled private evidence port.

Native rows/site/permissions are explicit doubles; this is not Group dispatch.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.adapters.sites.native_private_evidence import (
    NativePrivateEvidence,
    check_native_payload,
)
from lab_generate_skill.adapters.sites.private_artifacts import (
    OriginalSitePrivateArtifacts,
)
from lab_generate_skill.adapters.sites.storage_admission import (
    OriginalSiteStorageAdmission,
)
from lab_generate_skill.adapters.storage.managed_store import ManagedEvidenceStore
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.native_private_json import (
    GITLAB_PRIVATE_JSON,
    GITLAB_GROUP_PRIVATE_JSON,
    REDDIT_PRIVATE_JSON,
    NativePrivateJsonProfile,
)
from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    InvalidTransition,
    OperationStopped,
)
from lab_generate_skill.bootstrap.site_instance import build_site_instance
from lab_generate_skill.ports.lifecycle import OperationControl
from gitlab_group_fixtures import selected_spec, reference
from test_gitlab_private_evidence import c as c, Case as SshCase, Admission
from test_site_private_configuration import gitlab
from test_slurm_commands import guard


@dataclass
class GroupCase:
    transport: NativePrivateEvidence
    request: SiteTaskRequest
    original: SshCase
    admission: Admission


@pytest.fixture
def group(c: SshCase) -> GroupCase:
    plan = SitePrivateEvidencePlan.model_validate(
        c.transport.plan.model_copy(update={"profile": GITLAB_GROUP_PRIVATE_JSON})
    )
    admission = Admission(plan, c.transport.context)
    spec = selected_spec()
    request = SiteTaskRequest.model_validate(
        c.request.model_copy(
            update={
                "task": spec.task,
                "private_input": spec.model_dump_json(),
                "snapshot_ref": reference(b"{}").model_copy(
                    update={"content_schema": "gitlab-group-recovery/1"}
                ),
            }
        )
    )
    return GroupCase(
        NativePrivateEvidence(
            plan,
            c.transport.context,
            c.store,
            admission,
            profile=GITLAB_GROUP_PRIVATE_JSON,
        ),
        request,
        c,
        admission,
    )


def test_explicit_profile_roundtrip_publish_read_and_repeat_read(
    group: GroupCase,
) -> None:
    transport = group.transport
    assert transport.plan.schema_version == "site-private-evidence-plan/3"
    assert (
        SitePrivateEvidencePlan.model_validate_json(transport.plan.model_dump_json())
        == transport.plan
    )
    raw = b'{"synthetic_group_fact":true}'
    result = transport.publish(group.request, raw, control=guard())
    assert result.payload_ref.content_schema == GITLAB_GROUP_PRIVATE_JSON.content_schema
    assert result.payload_ref.producer == GITLAB_GROUP_PRIVATE_JSON.producer
    assert result.request_sha256 == group.request.digest
    assert transport.read(group.request, result, control=guard()) == raw
    assert transport.read(group.request, result, control=guard()) == raw
    assert group.admission.calls == ["publish", "read", "read"]
    for wrong in (GITLAB_PRIVATE_JSON, REDDIT_PRIVATE_JSON):
        with pytest.raises(EvidenceIntegrityError):
            check_native_payload(result.payload_ref, transport.plan, wrong)
    with pytest.raises(InvalidTransition):
        transport.publish(group.request, raw, control=guard())


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "null",
        "bool",
        "empty",
        "old",
        "old_with_profile",
        "foreign_site",
        "extra",
    ],
)
def test_declaration_has_no_profile_or_old_version_inference(
    c: SshCase, change: str
) -> None:
    config = gitlab(c).model_dump(mode="json")
    plan = config["private_evidence"]
    if change in ("missing", "old"):
        plan.pop("profile")
    if change in ("old", "old_with_profile"):
        plan["schema_version"] = "site-private-evidence-plan/2"
    elif change == "null":
        plan["profile"] = None
    elif change == "bool":
        plan["profile"] = True
    elif change == "empty":
        plan["profile"] = {}
    elif change == "foreign_site":
        plan["profile"] = REDDIT_PRIVATE_JSON.model_dump(mode="json")
    elif change == "extra":
        plan["profile"]["implicit_default"] = True
    with pytest.raises(ValueError):
        SiteWorkerConfiguration.model_validate_json(json.dumps(config))


@pytest.mark.parametrize(
    "field,value",
    [
        ("site_id", "reddit"),
        ("family", "profile_ssh_key"),
        ("content_schema", "gitlab-native-private-json/1"),
        ("producer", "fixed-gitlab-native-private-v1"),
        ("family", None),
        ("family", True),
        ("family", ""),
    ],
)
def test_profile_cannot_mix_group_ssh_or_other_site_variants(
    field: str, value: Any
) -> None:
    with pytest.raises(ValueError):
        NativePrivateJsonProfile.model_validate(
            {**GITLAB_GROUP_PRIVATE_JSON.model_dump(), field: value}
        )


def test_mismatched_profile_rejected_before_admission_or_put(group: GroupCase) -> None:
    with pytest.raises(OwnershipConflict):
        NativePrivateEvidence(
            group.transport.plan,
            group.transport.context,
            group.original.store,
            group.admission,
            profile=GITLAB_PRIVATE_JSON,
        )
    with pytest.raises(OwnershipConflict):
        group.transport.publish(group.original.request, b"{}", control=guard())
    assert group.admission.calls == [] and not group.transport.attempted


@pytest.mark.parametrize(
    "fault", ["before_commit", "lost_ack", "wrong_ref", "after_commit_cancel"]
)
def test_group_unknown_publication_keeps_raw_candidate_and_cannot_retry(
    group: GroupCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    original, calls = group.original.store.put, []
    primary = (
        OperationStopped("CANCELLED", "original-group-publication")
        if fault == "after_commit_cancel"
        else OSError("original lost acknowledgement")
    )

    def put(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        calls.append(raw)
        if fault == "before_commit":
            raise primary
        actual = original(raw, metadata, control=control)
        if fault != "wrong_ref":
            raise primary
        return actual.model_copy(update={"producer": "foreign"})

    monkeypatch.setattr(group.original.store, "put", put)
    with pytest.raises((OSError, OperationStopped, EvidenceIntegrityError)) as caught:
        group.transport.publish(group.request, b'{"complete":true}', control=guard())
    if fault != "wrong_ref":
        assert caught.value is primary
    candidate = group.transport.last_candidate
    assert candidate is not None and group.transport.quarantined
    if fault == "before_commit":
        assert not list(
            (Path(group.transport.plan.config.evidence_root) / "blobs").iterdir()
        )
    else:
        assert (
            group.original.store.read(candidate.payload_ref, control=guard())
            == b'{"complete":true}'
        )
    with pytest.raises(InvalidTransition):
        group.transport.publish(group.request, b"{}", control=guard())
    with pytest.raises(InvalidTransition):
        group.transport.read(group.request, candidate, control=guard())
    assert len(calls) == 1


def test_group_cancellation_before_admission_does_not_reserve_or_publish(
    group: GroupCase,
) -> None:
    error = OperationStopped("CANCELLED", "group-before-admission")

    class Control:
        def checkpoint(self) -> float:
            raise error

        def wait(self, seconds: float) -> None:
            raise AssertionError("Publication must not wait or retry")

    with pytest.raises(OperationStopped) as caught:
        group.transport.publish(group.request, b"{}", control=Control())
    assert caught.value is error and not group.transport.attempted
    assert group.admission.calls == []
    assert not list(
        (Path(group.transport.plan.config.evidence_root) / "blobs").iterdir()
    )


def test_declared_group_profile_is_inert_before_original_task_admission(
    c: SshCase, tmp_path: Path
) -> None:
    config = gitlab(c)
    assert config.private_evidence is not None
    config = SiteWorkerConfiguration.model_validate(
        config.model_copy(
            update={
                "private_evidence": config.private_evidence.model_copy(
                    update={"profile": GITLAB_GROUP_PRIVATE_JSON}
                )
            }
        )
    )
    before = tuple(tmp_path.rglob("*"))
    worker = build_site_instance(config, worker_guard=NoObservation())
    spec = selected_spec()
    request = c.request.model_copy(
        update={"task": spec.task, "private_input": spec.model_dump_json()}
    )
    with pytest.raises(InvalidTransition):
        worker.execute_task(request, control=guard())
    assert before == tuple(tmp_path.rglob("*"))


class NoObservation:
    def observe(self, control: OperationControl) -> Any:
        raise AssertionError("Profile declaration grants no acquisition")


def test_original_artifact_assembly_uses_declared_group_profile_and_stops_io(
    group: GroupCase,
) -> None:
    context, plan = group.transport.context, group.transport.plan

    class Store:
        initializes = 0

        def initialize(self, control: OperationControl) -> None:
            control.checkpoint()
            self.initializes += 1

        def put(
            self, raw: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            return group.original.store.put(raw, metadata, control=control)

        def read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
            return group.original.store.read(ref, control=control)

    class Binder(Admission):
        bound = False
        stopped = False

        def bind_instance(
            self, started: SiteInstanceStarted, control: OperationControl
        ) -> Any:
            control.checkpoint()
            assert started == context.instance
            if self.bound:
                raise InvalidTransition("Original instance already bound")
            self.bound = True
            return context

        def stop_new_io(self) -> None:
            self.stopped = True

    store, admission = Store(), Binder(plan, context)
    artifacts = OriginalSitePrivateArtifacts(
        plan,
        cast(ManagedEvidenceStore, store),
        cast(OriginalSiteStorageAdmission, admission),
    )
    artifacts.initialize(guard())
    artifacts.bind_instance(context.instance, guard())
    raw = b'{"synthetic_group":true}'
    result = artifacts.publish(group.request, raw, control=guard())
    assert result.payload_ref.content_schema == GITLAB_GROUP_PRIVATE_JSON.content_schema
    assert artifacts.read(group.request, result, control=guard()) == raw
    assert store.initializes == 1 and admission.calls == ["publish", "read"]
    with pytest.raises(InvalidTransition):
        artifacts.bind_instance(context.instance, guard())
    artifacts.stop_new_io()
    with pytest.raises(InvalidTransition):
        artifacts.read(group.request, result, control=guard())
    with pytest.raises(InvalidTransition):
        artifacts.publish(group.request, raw, control=guard())
    assert admission.stopped and store.initializes == 1
