"""Full original environment/reset facts; no real geographic DB or browser claim."""

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeIntent, SiteResumeResult
from lab_generate_skill.domain.reset import assemble_reset
from lab_generate_skill.sites.map.tasks.overlay_policy import overlay_initial_spec
from lab_generate_skill.sites.map.tasks.overlay_recovery import OverlayResumed
from map_qualification_fixtures import qualified, restore
from map_registered_worker_fixtures import RegisteredMapCase
from preparation_record_fixtures import put
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


class Cancel:
    def checkpoint(self) -> float:
        raise OperationStopped("CANCELLED", "qualification")

    def wait(self, seconds: float) -> None:
        self.checkpoint()


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "site",
        "started",
        "coverage",
        "scope",
        "snapshot",
        "missing",
        "corrupt",
        "cancel",
        "denied",
        "operation-run",
        "operation-owner",
        "operation-attempt",
        "operation-allocation",
        "operation-recovery",
    ],
)
def test_environment_requires_complete_original_configured_facts(
    fault: str, registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = registered_map
    with qualified(original, monkeypatch) as c:
        store = original.resource.evidence
        env = c.environment
        original.observer = "controller"
        if fault == "site":
            site = original.resource.spec
            changed = site.model_copy(
                update={
                    "configuration": site.configuration.model_copy(
                        update={"apptainer": "/foreign/apptainer"}
                    )
                }
            )
            env = env.model_copy(update={"site_spec_ref": put(store, changed)})
        if fault == "started":
            changed_start = c.live.site.model_copy(
                update={
                    "instance": c.live.site.instance.model_copy(
                        update={"endpoint": "http://127.0.0.1:65535/"}
                    )
                }
            )
            env = env.model_copy(update={"site_started_ref": put(store, changed_start)})
        if fault == "coverage":
            spec = overlay_initial_spec(original.scope.task).model_copy(
                update={"environment_checks": ("narrow",)}
            )
            env = env.model_copy(update={"spec_ref": put(store, spec)})
        if fault == "scope":
            env = env.model_copy(
                update={"scope": env.scope.model_copy(update={"context_id": "foreign"})}
            )
        if fault == "snapshot":
            env = env.model_copy(
                update={"snapshot_ref": put(store, c.preparation.observed)}
            )
        if fault in ("missing", "corrupt"):
            native = c.preparation.snapshot.native
            manifest = json.loads(
                (
                    Path(native.plan.private_root) / "published/manifest.json"
                ).read_bytes()
            )
            path = Path(manifest["artifact"]["root"]) / "state.json"
            if fault == "missing":
                path.parent.chmod(0o700)
                path.unlink()
            else:
                path.chmod(0o600)
                path.write_bytes(b"corrupt")
        operation = c.preparation.environment.operation
        fields = {
            "operation-run": "run_id",
            "operation-owner": "owner_id",
            "operation-attempt": "attempt_id",
            "operation-allocation": "allocation_id",
            "operation-recovery": "recovery_ref",
        }
        if fault in fields:
            operation = operation.model_copy(
                update={
                    fields[fault]: None if fault == "operation-recovery" else "foreign"
                }
            )
        calls = (len(original.case.commands.calls), len(original.generation.groups))
        if fault == "none":
            ref = c.qualifications.publish_environment(c.environment_ref, operation)
            for _ in range(2):
                loaded = c.qualifications.load_environment(
                    c.environment_ref, ref, operation
                )
                assert (
                    loaded == c.preparation.environment
                    and loaded.checks.status == "pass"
                )
        elif fault == "denied":
            c.authority.denied = True
            with pytest.raises(PermissionError, match="denied"):
                c.qualifications.publish_environment(c.environment_ref, operation)
        else:
            with pytest.raises(
                (
                    ValueError,
                    EvidenceError,
                    OwnershipConflict,
                    OperationStopped,
                    FileNotFoundError,
                )
            ):
                c.qualifications.checks.environment(
                    env,
                    put(store, env),
                    operation,
                    Cancel() if fault == "cancel" else guard(),
                )
        assert calls == (
            len(original.case.commands.calls),
            len(original.generation.groups),
        )


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "forced",
        "closure",
        "foreign-closure",
        "plan",
        "restore",
        "resume",
        "intent",
        "generation",
        "namespace",
        "native",
        "missing",
        "cancel",
    ],
)
def test_reset_requires_original_closed_attempt_and_complete_resume(
    fault: str, registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = registered_map
    with qualified(original, monkeypatch) as c:
        store = original.resource.evidence
        selected = restore(c, forced=fault == "forced")
        if fault in ("closure", "foreign-closure"):
            closure = ClosureReceipt.model_validate_json(
                store.read(selected.closure_refs[0])
            )
            closure = (
                closure.model_copy(update={"status": "unconfirmed"})
                if fault == "closure"
                else closure.model_copy(
                    update={
                        "token": closure.token.model_copy(
                            update={"allocation_id": "foreign"}
                        )
                    }
                )
            )
            selected = selected.model_copy(
                update={"closure_refs": (put(store, closure),)}
            )
        if fault == "plan":
            selected = selected.model_copy(
                update={
                    "plan_ref": put(
                        store,
                        c.plan.model_copy(update={"parent_operation_id": "foreign"}),
                    )
                }
            )
        if fault == "restore":
            restored = SiteTaskResult.model_validate_json(
                store.read(selected.restore_result_ref)
            )
            selected = selected.model_copy(
                update={
                    "restore_result_ref": put(
                        store, restored.model_copy(update={"request_sha256": "f" * 64})
                    )
                }
            )
        if fault == "intent":
            intent = SiteResumeIntent.model_validate_json(
                store.read(selected.resume_intent_ref)
            )
            selected = selected.model_copy(
                update={
                    "resume_intent_ref": put(
                        store,
                        intent.model_copy(update={"configuration_sha256": "f" * 64}),
                    )
                }
            )
        resumed = SiteResumeResult.model_validate_json(
            store.read(selected.resume_result_ref)
        )
        observed = OverlayResumed.model_validate_json(resumed.private_result)
        if fault == "resume":
            resumed = resumed.model_copy(update={"request_sha256": "f" * 64})
        if fault == "generation":
            stopped = observed.resumed.cleared.stopped.model_copy(
                update={"generation": 2}
            )
            reset = observed.resumed.model_copy(
                update={
                    "cleared": observed.resumed.cleared.model_copy(
                        update={"stopped": stopped}
                    )
                }
            )
            observed = observed.model_copy(update={"resumed": reset})
        if fault == "namespace":
            ns = observed.resumed.frontend
            ns = ns.model_copy(
                update={
                    "launcher": ns.launcher.model_copy(update={"start_ticks": 1}),
                    "init": ns.init.model_copy(update={"start_ticks": 2}),
                }
            )
            observed = observed.model_copy(
                update={"resumed": observed.resumed.model_copy(update={"frontend": ns})}
            )
        if fault == "native":
            native = observed.native.model_copy(
                update={
                    "file": observed.native.file.model_copy(update={"sha256": "f" * 64})
                }
            )
            observed = observed.model_copy(update={"native": native})
        if fault in ("generation", "namespace", "native"):
            resumed = resumed.model_copy(
                update={"private_result": observed.model_dump_json()}
            )
        if fault in ("resume", "generation", "namespace", "native"):
            selected = selected.model_copy(
                update={"resume_result_ref": put(store, resumed)}
            )
        if fault == "missing":
            manifest = json.loads(
                (
                    Path(observed.native.plan.private_root) / "published/manifest.json"
                ).read_bytes()
            )
            path = Path(manifest["artifact"]["root"]) / "state.json"
            path.parent.chmod(0o700)
            path.unlink()
        ref = put(store, selected)
        calls = (len(original.case.commands.calls), len(original.generation.groups))
        if fault in ("none", "forced"):
            op = c.preparation.request.operation.cleanup(
                "qualify-reset", now=datetime.now(timezone.utc), seconds=30
            ).model_copy(update={"recovery_ref": c.plan.environment_recovery_ref})
            inputs = c.qualifications.publish_reset_facts(ref, op)
            final = op.model_copy(update={"operation_id": "assemble-reset"})
            assert assemble_reset(inputs, final).status == "safe"
            assert (
                c.qualifications.checks.reset(selected, ref, guard()).health.status
                == "pass"
            )
            assert observed.resumed.cleared.stopped.forced_namespace == (
                fault == "forced"
            )
        else:
            with pytest.raises(
                (
                    ValueError,
                    EvidenceError,
                    OwnershipConflict,
                    OperationStopped,
                    FileNotFoundError,
                )
            ):
                c.qualifications.checks.reset(
                    selected, ref, Cancel() if fault == "cancel" else guard()
                )
        assert calls == (
            len(original.case.commands.calls),
            len(original.generation.groups),
        )


@pytest.mark.parametrize(
    "value", [None, False, 0, "", [], {}, {"schema_version": "environment-selection/0"}]
)
def test_qualification_selection_rejects_empty_wrong_type_and_old_schema(
    value: object,
) -> None:
    from lab_generate_skill.domain.state_qualification import (
        EnvironmentSelection,
        ResetSelection,
    )

    for model in (EnvironmentSelection, ResetSelection):
        with pytest.raises(ValueError):
            model.model_validate(value)
