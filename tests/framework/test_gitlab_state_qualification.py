"""Selected full native environment/reset records, with explicit synthetic authority."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_ssh_state import load_ssh_key_state
from lab_generate_skill.sites.gitlab.tasks.ssh_key_state_checks import SshKeyStateChecks
from lab_generate_skill.bootstrap.gitlab_ssh_records import gitlab_state_qualifications
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.domain.lifecycle import AllocationToken, ClosureReceipt
from lab_generate_skill.domain.errors import EvidenceError, OwnershipConflict
from gitlab_qualification_fixtures import qualified, restore
from gitlab_preparation_fixtures import put
from test_resource_journal import NoCancellation
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "image",
        "site",
        "release",
        "guard",
        "coverage",
        "snapshot",
        "missing_native",
        "profile",
        "denied",
    ],
)
def test_original_six_service_environment_cannot_change_pins_or_full_coverage(
    tmp_path: Path,
    node_path: Path,
    fault: str,
) -> None:
    with qualified(tmp_path, node_path) as c:
        p, env = c.preparation, c.environment
        if fault in ("image", "site"):
            config = c.site.configuration
            if fault == "image":
                config = config.model_copy(
                    update={
                        "files": config.files.model_copy(
                            update={
                                "image": config.files.image.model_copy(
                                    update={"sha256": "f" * 64}
                                )
                            }
                        )
                    }
                )
            else:
                config = config.model_copy(
                    update={
                        "token": config.token.model_copy(
                            update={"allocation_id": "foreign"}
                        )
                    }
                )
            env = env.model_copy(
                update={
                    "site_spec_ref": put(
                        p.store, c.site.model_copy(update={"configuration": config})
                    )
                }
            )
        elif fault in ("release", "guard"):
            ready = c.started.ready
            if fault == "guard":
                worker = ready.worker.model_copy(
                    update={
                        "owner_guard": ready.worker.owner_guard.model_copy(
                            update={
                                "controller": ready.worker.owner_guard.controller.model_copy(
                                    update={"start_ticks": 2}
                                )
                            }
                        )
                    }
                )
            else:
                worker = ready.worker.model_copy(
                    update={
                        "installed_sources": ready.worker.installed_sources.model_copy(
                            update={"release_id": "foreign"}
                        )
                    }
                )
            changed = c.started.model_copy(
                update={"ready": ready.model_copy(update={"worker": worker})}
            )
            env = env.model_copy(update={"site_started_ref": put(p.store, changed)})
        elif fault == "profile":
            from lab_generate_skill.domain.native_private_json import (
                GITLAB_GROUP_PRIVATE_JSON,
            )

            cfg = c.site.configuration
            assert cfg.private_evidence is not None
            cfg = cfg.model_copy(
                update={
                    "private_evidence": cfg.private_evidence.model_copy(
                        update={"profile": GITLAB_GROUP_PRIVATE_JSON}
                    )
                }
            )
            env = env.model_copy(
                update={
                    "site_spec_ref": put(
                        p.store, c.site.model_copy(update={"configuration": cfg})
                    )
                }
            )
        elif fault == "coverage":
            env = env.model_copy(
                update={
                    "spec_ref": put(
                        p.store,
                        p.inputs.spec.model_copy(
                            update={"environment_checks": ("narrow",)}
                        ),
                    )
                }
            )
        elif fault == "snapshot":
            env = env.model_copy(update={"snapshot_ref": put(p.store, p.inputs.spec)})
        elif fault == "missing_native":
            assert p.native.task.snapshot is not None
            (
                node_path
                / "private-evidence/blobs"
                / p.native.task.snapshot.native_before.payload_ref.sha256
            ).unlink()
        op = p.inputs.environment.operation
        before = p.native.reader.calls
        if fault == "none":
            checked = SshKeyStateChecks(p.store, load_ssh_key_state).environment(
                env, put(p.store, env), op, guard()
            )
            assert (
                checked.checks.status == "pass" and checked.allocation == c.site.token
            )
        elif fault == "denied":
            c.authority.denied = True
            records = gitlab_state_qualifications(
                p.store, OperationGuards(SystemClock(), NoCancellation()), c.authority
            )
            with pytest.raises(PermissionError):
                records.publish_environment(c.environment_ref, op)
        else:
            with pytest.raises((ValueError, EvidenceError, OwnershipConflict)):
                SshKeyStateChecks(p.store, load_ssh_key_state).environment(
                    env, put(p.store, env), op, guard()
                )
        assert p.native.reader.calls == before


@pytest.mark.parametrize(
    "fault", ["none", "closure", "plan", "restore", "resume", "intent", "recovery"]
)
def test_full_restore_resume_records_require_original_closures_and_native_baseline(
    tmp_path: Path,
    node_path: Path,
    fault: str,
) -> None:
    with qualified(tmp_path, node_path) as c:
        p = c.preparation
        assert p.inputs.request.operation.recovery_ref is not None
        token = AllocationToken(
            allocation_id="synthetic-browser",
            owner=c.environment.scope.owner,
            scope="attempt",
            attempt_id=c.environment.scope.attempt_id,
            resource_kind="browser",
            expected_resource_id="synthetic-browser",
            provider_id="fixed-browser-worker",
            provider_version="3",
            recovery_ref=p.inputs.request.operation.recovery_ref,
        )
        closure = ClosureReceipt(
            token=token,
            operation_id="original-close",
            status="closed",
            evidence=(c.environment.spec_ref,),
        )
        ref = put(p.store, closure)
        selection = restore(c, (token,), (ref,))
        if fault == "closure":
            selection = selection.model_copy(
                update={
                    "closure_refs": (
                        put(
                            p.store,
                            closure.model_copy(update={"status": "unconfirmed"}),
                        ),
                    )
                }
            )
        elif fault == "plan":
            from lab_generate_skill.domain.reset import ResetPlan

            plan = ResetPlan.model_validate_json(p.store.read(selection.plan_ref))
            selection = selection.model_copy(
                update={
                    "plan_ref": put(
                        p.store,
                        plan.model_copy(update={"parent_operation_id": "foreign"}),
                    )
                }
            )
        elif fault in ("restore", "resume", "intent", "recovery"):
            from lab_generate_skill.domain.site_task import SiteTaskResult
            from lab_generate_skill.domain.site_resume import (
                SiteResumeResult,
                SiteResumeIntent,
            )

            if fault == "restore":
                result = SiteTaskResult.model_validate_json(
                    p.store.read(selection.restore_result_ref)
                )
                selection = selection.model_copy(
                    update={
                        "restore_result_ref": put(
                            p.store,
                            result.model_copy(update={"request_sha256": "f" * 64}),
                        )
                    }
                )
            elif fault == "resume":
                resumed = SiteResumeResult.model_validate_json(
                    p.store.read(selection.resume_result_ref)
                )
                selection = selection.model_copy(
                    update={
                        "resume_result_ref": put(
                            p.store,
                            resumed.model_copy(update={"request_sha256": "f" * 64}),
                        )
                    }
                )
            elif fault == "intent":
                intent = SiteResumeIntent.model_validate_json(
                    p.store.read(selection.resume_intent_ref)
                )
                selection = selection.model_copy(
                    update={
                        "resume_intent_ref": put(
                            p.store,
                            intent.model_copy(
                                update={"configuration_sha256": "f" * 64}
                            ),
                        )
                    }
                )
            else:
                from lab_generate_skill.domain.lifecycle import RecoveryPlan
                from lab_generate_skill.domain.reset import ResetPlan

                plan = ResetPlan.model_validate_json(p.store.read(selection.plan_ref))
                recovery = RecoveryPlan.model_validate_json(
                    p.store.read(plan.task_recovery_ref)
                )
                plan = plan.model_copy(
                    update={
                        "task_recovery_ref": put(
                            p.store,
                            recovery.model_copy(
                                update={"restore_component_id": "foreign"}
                            ),
                        )
                    }
                )
                selection = selection.model_copy(
                    update={"plan_ref": put(p.store, plan)}
                )
        before = p.native.reader.calls
        checks = SshKeyStateChecks(p.store, load_ssh_key_state)
        if fault == "none":
            assert (
                checks.reset(selection, put(p.store, selection), guard()).health.status
                == "pass"
            )
            records = gitlab_state_qualifications(
                p.store, OperationGuards(SystemClock(), NoCancellation()), c.authority
            )
            op = p.inputs.request.operation.cleanup(
                "record-reset", now=datetime.now(timezone.utc), seconds=30
            ).model_copy(update={"recovery_ref": c.site.token.recovery_ref})
            recorded = records.publish_reset_facts(put(p.store, selection), op)
            assert (
                recorded.task.checks.status
                == recorded.environment.checks.status
                == recorded.health.checks.status
                == "pass"
            )
        else:
            with pytest.raises((ValueError, EvidenceError, OwnershipConflict)):
                checks.reset(selection, put(p.store, selection), guard())
        assert p.native.reader.calls == before
