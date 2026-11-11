"""Complete declared scope, immutable facts and no qualification from unknowns."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.reset import assemble_reset
from lab_generate_skill.adapters.plans.reset_evidence import ResetEvidenceReader
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeResult
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceNotFound,
    EvidenceIntegrityError,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_state_policy import (
    product_initial_state_spec,
)
from state_qualification_fixtures import qualified
from site_instance_fixtures import node_path as node_path
from preparation_record_fixtures import put
from test_slurm_commands import guard


def test_original_environment_and_complete_reset_recompute(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with qualified(tmp_path, node_path, monkeypatch) as c:
        records = c["records"]
        baseline = records.load_environment(
            c["selection_ref"], c["environment_ref"], c["operation"]
        )
        assert (
            baseline.checks.status == "pass"
            and baseline.measured_state_sha256 == c["snapshot"].state.digest
        )
        facts = records.publish_reset_facts(c["reset_ref"], c["reset_op"])
        reset = assemble_reset(facts, c["reset_op"])
        assert reset.status == "safe" and all(
            x.checks.status == "pass"
            for x in (facts.task, facts.environment, facts.health)
        )
        assert ResetEvidenceReader(c["store"]).verify(reset, guard()) == facts
        assert (
            facts.task.checks.required
            == product_initial_state_spec(facts.plan.scope.task).task_reset_checks
        )
        assert facts.task.after_closure_refs == c["reset"].closure_refs
        assert (
            records.load_environment(
                c["selection_ref"], c["environment_ref"], c["operation"]
            )
            == baseline
        )


@pytest.mark.parametrize(
    "fault",
    [
        "snapshot_digest",
        "artifact_scope",
        "environment_policy",
        "legacy_recovery",
        "binding_spec",
        "site_image",
    ],
)
def test_environment_rejects_incomplete_or_foreign_facts(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with qualified(tmp_path, node_path, monkeypatch) as c:
        store, selection = c["store"], c["environment"]
        checks = c["records"].checks
        if fault == "snapshot_digest":
            selection = selection.model_copy(
                update={
                    "snapshot_ref": selection.snapshot_ref.model_copy(
                        update={"sha256": "f" * 64}
                    )
                }
            )
        elif fault == "artifact_scope":
            snap = c["snapshot"]
            layout = snap.state.plan.artifacts.model_copy(
                update={"paths": ("var/training-mail",)}
            )
            state = snap.state.model_copy(
                update={
                    "plan": snap.state.plan.model_copy(update={"artifacts": layout}),
                    "artifacts": snap.state.artifacts.model_copy(
                        update={"layout": layout, "tree_sha256": (None,)}
                    ),
                }
            )
            selection = selection.model_copy(
                update={
                    "snapshot_ref": put(store, snap.model_copy(update={"state": state}))
                }
            )
        elif fault == "environment_policy":
            from lab_generate_skill.domain.state_checks import InitialStateSpec

            spec = InitialStateSpec.model_validate_json(store.read(selection.spec_ref))
            selection = selection.model_copy(
                update={
                    "spec_ref": put(
                        store,
                        spec.model_copy(
                            update={
                                "environment_checks": ("admin.environment.complete",)
                            }
                        ),
                    )
                }
            )
        elif fault == "binding_spec":
            snap = c["snapshot"]
            from lab_generate_skill.domain.task import TaskBinding

            binding = TaskBinding.model_validate_json(
                store.read(snap.request.binding_ref)
            )
            request = snap.request.model_copy(
                update={
                    "binding_ref": put(
                        store,
                        binding.model_copy(
                            update={
                                "baseline_ref": binding.baseline_ref.model_copy(
                                    update={"sha256": "f" * 64}
                                )
                            }
                        ),
                    )
                }
            )
            selection = selection.model_copy(
                update={
                    "snapshot_ref": put(
                        store, snap.model_copy(update={"request": request})
                    )
                }
            )
        else:
            from lab_generate_skill.domain.site_resource import SiteResourceSpec

            site = SiteResourceSpec.model_validate_json(
                store.read(selection.site_spec_ref)
            )
            if fault == "legacy_recovery":
                from lab_generate_skill.domain.lifecycle import RecoveryPlan

                old = RecoveryPlan.model_validate_json(
                    store.read(site.token.recovery_ref)
                ).model_copy(
                    update={
                        "restore_component_id": "site-close",
                        "restore_component_version": "2",
                        "state_coverage": ("site-processes",),
                    }
                )
                config = site.configuration.model_copy(
                    update={
                        "token": site.token.model_copy(
                            update={"recovery_ref": put(store, old)}
                        )
                    }
                )
            else:
                config = site.configuration.model_copy(
                    update={
                        "files": site.configuration.files.model_copy(
                            update={
                                "image": site.configuration.files.image.model_copy(
                                    update={"sha256": "f" * 64}
                                )
                            }
                        )
                    }
                )
            selection = selection.model_copy(
                update={
                    "site_spec_ref": put(
                        store, site.model_copy(update={"configuration": config})
                    )
                }
            )
        with pytest.raises(
            (ValueError, OwnershipConflict, EvidenceNotFound, EvidenceIntegrityError)
        ):
            checks.environment(
                selection, put(store, selection), c["operation"], guard()
            )


@pytest.mark.parametrize(
    "fault",
    [
        "state_digest",
        "restore_request",
        "resume_state",
        "resume_intent",
        "closure_unknown",
        "no_browser",
        "task_coverage",
    ],
)
def test_reset_cannot_drop_or_substitute_original_evidence(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with qualified(tmp_path, node_path, monkeypatch) as c:
        store, selection = c["store"], c["reset"]
        if fault == "state_digest":
            restored = c["restored"].model_copy(
                update={
                    "state": c["restored"].state.model_copy(
                        update={"snapshot_sha256": "f" * 64}
                    )
                }
            )
            result = SiteTaskResult.model_validate_json(
                store.read(selection.restore_result_ref)
            ).model_copy(update={"private_result": restored.model_dump_json()})
            selection = selection.model_copy(
                update={"restore_result_ref": put(store, result)}
            )
        elif fault == "restore_request":
            result = SiteTaskResult.model_validate_json(
                store.read(selection.restore_result_ref)
            ).model_copy(update={"request_sha256": "f" * 64})
            selection = selection.model_copy(
                update={"restore_result_ref": put(store, result)}
            )
        elif fault == "resume_state":
            recovered = c["resumed"].model_copy(
                update={"state_restored_sha256": "f" * 64}
            )
            resume_result = SiteResumeResult.model_validate_json(
                store.read(selection.resume_result_ref)
            ).model_copy(update={"private_result": recovered.model_dump_json()})
            selection = selection.model_copy(
                update={"resume_result_ref": put(store, resume_result)}
            )
        elif fault == "resume_intent":
            from lab_generate_skill.domain.site_resume import SiteResumeIntent

            intent = SiteResumeIntent.model_validate_json(
                store.read(selection.resume_intent_ref)
            ).model_copy(update={"configuration_sha256": "f" * 64})
            selection = selection.model_copy(
                update={"resume_intent_ref": put(store, intent)}
            )
        elif fault == "closure_unknown":
            from lab_generate_skill.domain.lifecycle import ClosureReceipt

            closure = ClosureReceipt.model_validate_json(
                store.read(selection.closure_refs[0])
            ).model_copy(update={"status": "unconfirmed"})
            selection = selection.model_copy(
                update={"closure_refs": (put(store, closure),)}
            )
        else:
            from lab_generate_skill.domain.reset import ResetPlan

            plan = ResetPlan.model_validate_json(store.read(selection.plan_ref))
            if fault == "no_browser":
                plan = plan.model_copy(
                    update={
                        "attempt_allocations": (
                            plan.attempt_allocations[0].model_copy(
                                update={"resource_kind": "generator"}
                            ),
                        )
                    }
                )
            else:
                from lab_generate_skill.domain.lifecycle import RecoveryPlan

                rec = RecoveryPlan.model_validate_json(
                    store.read(plan.task_recovery_ref)
                ).model_copy(update={"state_coverage": ("admin.product.absent",)})
                plan = plan.model_copy(update={"task_recovery_ref": put(store, rec)})
            selection = selection.model_copy(update={"plan_ref": put(store, plan)})
        with pytest.raises((ValueError, OwnershipConflict)):
            c["records"].publish_reset_facts(put(store, selection), c["reset_op"])


def test_authority_denied_and_wrong_owner_no_publication(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with qualified(tmp_path, node_path, monkeypatch) as c:
        before = set((tmp_path / "evidence/blobs").iterdir())
        c["authority"].denied = True
        with pytest.raises(PermissionError):
            c["records"].publish_reset_facts(c["reset_ref"], c["reset_op"])
        with pytest.raises(OwnershipConflict):
            c["records"].publish_reset_facts(
                c["reset_ref"],
                c["reset_op"].model_copy(
                    update={"operation_id": "foreign", "owner_id": "foreign"}
                ),
            )
        assert set((tmp_path / "evidence/blobs").iterdir()) == before


@pytest.mark.parametrize(
    "phase", ["task-reset/1", "environment-reset/1", "reset-health/1"]
)
def test_partial_commit_retains_prefix_and_unknown_candidate(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    with qualified(tmp_path, node_path, monkeypatch) as c:
        original = c["store"].put

        def broken(data: bytes, metadata: Any, control: Any) -> Any:
            result = original(data, metadata, control)
            if metadata.content_schema == phase:
                raise OSError("ack lost after actual put")
            return result

        monkeypatch.setattr(c["store"], "put", broken)
        with pytest.raises(OSError) as caught:
            c["records"].publish_reset_facts(c["reset_ref"], c["reset_op"])
        candidate = getattr(caught.value, "qualification_candidate_reference")
        assert candidate.content_schema == phase and c["store"].read(candidate)
        assert len(getattr(caught.value, "qualification_references")) == [
            "task-reset/1",
            "environment-reset/1",
            "reset-health/1",
        ].index(phase)


@pytest.mark.parametrize(
    "model,field,value",
    [
        (EnvironmentSelection, "snapshot_ref", None),
        (EnvironmentSelection, "schema_version", "old/1"),
        (ResetSelection, "closure_refs", ()),
        (ResetSelection, "schema_version", "old/1"),
    ],
)
def test_invalid_selection_shapes_rejected(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model: Any,
    field: str,
    value: Any,
) -> None:
    with qualified(tmp_path, node_path, monkeypatch) as c:
        data = (
            c["environment"] if model is EnvironmentSelection else c["reset"]
        ).model_dump()
        with pytest.raises(ValueError):
            model.model_validate({**data, field: value})
