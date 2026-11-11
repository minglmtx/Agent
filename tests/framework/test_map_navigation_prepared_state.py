"""Whole selected8 preparation consumers, no native website/Actor/source grant."""

import hashlib
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.preparation import PreparationReceipt
from lab_generate_skill.domain.site_resume import SiteResumeIntent
from lab_generate_skill.sites.map.tasks.navigation_recovery import NavigationResumed
from lab_generate_skill.sites.map.tasks.navigation_preparation_checks import (
    NavigationPreparationChecks,
)
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from lab_generate_skill.sites.map.tasks.overlay_preparation_checks import (
    OverlayPreparationChecks,
)
from map_navigation_group_cases import SOURCES
from map_registered_worker_fixtures import RegisteredMapCase
from map_navigation_prepared_fixtures import prepare_navigation
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from test_site_resource import enter, inspect
from test_slurm_commands import guard
from site_resume_fixtures import Authority as ResumeAuthority


@pytest.mark.parametrize("source", SOURCES)
def test_each_member_registered_preparation_exact_binding_full_state_and_readonly_repeat(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source)
    assert isinstance(c.private, NavigationSpec)
    try:
        with enter(c.resource) as live:
            p = prepare_navigation(c, live)
            assert isinstance(p.records.checks, NavigationPreparationChecks)
            assert p.environment.checks.status == "unknown"
            assert c.worker is not None and c.worker.references is None
            c.observer = "controller"
            try:
                before = len(c.sql.calls)
                prepared = p.records.load(p.publication, p.request.operation)
                receipt = PreparationReceipt.model_validate_json(
                    c.resource.evidence.read(
                        p.publication.preparation_ref, control=guard()
                    )
                )
                assert prepared.scope == c.scope and receipt.checks.status == "pass"
                assert p.records.load(p.publication, p.request.operation) == prepared
                assert len(c.sql.calls) == before
                inputs = p.records.reader.load(
                    p.publication.selection, p.request.operation, guard()
                )
                assert (
                    inputs.public_task.identity
                    == inputs.binding.identity
                    == c.scope.task
                )
                assert inputs.public_task.start_url.endswith(
                    c.private.original_start_path
                )
                with pytest.raises((ValueError, OwnershipConflict)):
                    OverlayPreparationChecks(
                        c.resource.evidence, p.records.checks.files
                    ).check(inputs, guard())
            finally:
                c.observer = "worker"
            restored = live.tasks.execute_task(c.request("restore"), control=guard())
            resume = c.resume_request(restored)
            intent = put(
                c.resource.evidence,
                SiteResumeIntent(
                    configuration_sha256=hashlib.sha256(
                        c.configuration.model_dump_json().encode()
                    ).hexdigest(),
                    request=resume,
                ),
            )
            returned = live.resume.resume_frontend(
                resume, intent, ResumeAuthority(c.resource.evidence), control=guard()
            )
            proof = NavigationResumed.model_validate_json(returned.private_result)
            assert proof.native.state_sha256 == p.snapshot.native.state_sha256
            assert c.worker.tasks is not None and c.worker.tasks.phase == "resumed"
        assert inspect(c.resource).state == "closed" and c.worker.closed
    finally:
        c.close_sockets()


@pytest.mark.parametrize(
    "fault",
    [
        "environment",
        "public",
        "coverage",
        "recovery",
        "private",
        "snapshot",
        "native-hash",
        "cancel",
    ],
)
def test_navigation_preparation_rejects_changed_scope_facts_and_cancel_without_query(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with enter(c.resource) as live:
            p = prepare_navigation(c, live)
            c.observer = "controller"
            try:
                inputs = p.records.reader.load(
                    p.publication.selection, p.request.operation, guard()
                )
                if fault == "environment":
                    inputs = inputs.model_copy(
                        update={
                            "environment": inputs.environment.model_copy(
                                update={"measured_state_sha256": "f" * 64}
                            )
                        }
                    )
                if fault == "public":
                    inputs = inputs.model_copy(
                        update={
                            "public_task": inputs.public_task.model_copy(
                                update={"goal": "other task"}
                            )
                        }
                    )
                if fault == "coverage":
                    inputs = inputs.model_copy(
                        update={
                            "spec": inputs.spec.model_copy(
                                update={"preparation_checks": ("other",)}
                            )
                        }
                    )
                if fault == "recovery":
                    inputs = inputs.model_copy(
                        update={
                            "recovery": inputs.recovery.model_copy(
                                update={"restore_component_id": "map-native-overlay"}
                            )
                        }
                    )
                if fault == "private":
                    other = c.private.model_copy(
                        update={
                            "native_contract_ref": c.private.native_contract_ref.model_copy(
                                update={"producer": "foreign"}
                            )
                        }
                    )
                    inputs = inputs.model_copy(
                        update={
                            "binding": inputs.binding.model_copy(
                                update={
                                    "private_spec_ref": put(c.resource.evidence, other)
                                }
                            )
                        }
                    )
                if fault in ("snapshot", "native-hash"):
                    observed = p.observed
                    if fault == "snapshot":
                        observed = observed.model_copy(
                            update={
                                "snapshot": observed.snapshot.model_copy(
                                    update={"schema_version": "map-overlay-snapshot/1"}
                                )
                            }
                        )
                    else:
                        observed = observed.model_copy(
                            update={
                                "native": observed.native.model_copy(
                                    update={"state_sha256": "f" * 64}
                                )
                            }
                        )
                    inputs = inputs.model_copy(
                        update={
                            "result": SiteTaskResult(
                                request_sha256=p.request.digest,
                                private_result=observed.model_dump_json(),
                            )
                        }
                    )

                class Cancel:
                    def checkpoint(self) -> float:
                        raise OperationStopped(
                            "CANCELLED", "navigation8-prepared-reader"
                        )

                    def wait(self, seconds: float) -> None:
                        self.checkpoint()

                before = len(c.sql.calls)
                with pytest.raises(
                    (
                        ValueError,
                        OwnershipConflict,
                        EvidenceIntegrityError,
                        OperationStopped,
                    )
                ):
                    p.records.checks.check(
                        inputs, Cancel() if fault == "cancel" else guard()
                    )
                assert len(c.sql.calls) == before
            finally:
                c.observer = "worker"
    finally:
        c.close_sockets()


@pytest.mark.parametrize("value", [None, "", {}, [], False, {"schema_version": "old"}])
def test_navigation_preparation_invalid_empty_and_wrong_type_never_reads(
    value: Any,
) -> None:
    class NoIO:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError("Invalid preparation cannot reach " + name)

    # Explicitly wrong object is an input-boundary fixture, never an authority.
    checks = NavigationPreparationChecks(NoIO(), NoIO())
    with pytest.raises(ValueError):
        checks.check(value, guard())
