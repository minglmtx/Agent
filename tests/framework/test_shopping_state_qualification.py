"""Original environment/preparation/reset reconstruction over actual CAS."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.reset import assemble_reset
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparationInputs,
)
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.sites.shopping.tasks.order_eta_preparation_checks import (
    OrderEtaPreparationChecks,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_recovery import OrderEtaResumed
from shopping_qualification_fixtures import qualified
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_original_environment_preparation_and_full_reset(
    node_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with qualified(tmp_path, node_path, monkeypatch) as c:
        environment = c["records"].load_environment(
            c["selection_ref"], c["environment_ref"], c["operation"]
        )
        assert environment.checks.status == "pass"
        store = c["store"]
        request = c["prepare"]
        result = c["preparation"]
        spec = c["spec"]
        selection = PreparationSelection(
            request_ref=put(store, request),
            result_ref=put(store, result),
            environment_ref=c["environment_ref"],
        )
        recovery = RecoveryPlan.model_validate_json(
            store.read(c["plan"].task_recovery_ref, control=guard())
        )
        inputs = PreparationInputs(
            selection=selection,
            request=request,
            result=result,
            binding=c["binding"],
            public_task=c["public"],
            spec=spec,
            environment=environment,
            recovery=recovery,
        )
        assert OrderEtaPreparationChecks(store).check(inputs, guard()).status == "pass"
        reset_inputs = c["records"].publish_reset_facts(c["reset_ref"], c["reset_op"])
        reset = assemble_reset(reset_inputs, c["reset_op"])
        assert reset.status == "safe"
        assert all(
            x.checks.status == "pass"
            for x in (reset_inputs.task, reset_inputs.environment, reset_inputs.health)
        )


@pytest.mark.parametrize(
    "fault",
    ["policy", "binding", "private_input", "image", "ports", "worker_boot", "recovery"],
)
def test_changed_environment_cannot_publish_pass(
    node_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with qualified(tmp_path, node_path, monkeypatch) as c:
        env = c["environment"]
        store = c["store"]
        snapshot = c["snapshot"]
        if fault == "policy":
            env = env.model_copy(
                update={
                    "spec_ref": put(
                        store,
                        c["spec"].model_copy(
                            update={"environment_checks": ("incomplete",)}
                        ),
                    )
                }
            )
        elif fault == "private_input":
            changed = snapshot.request.model_copy(
                update={
                    "private_input": snapshot.request.private_input.replace(
                        "2023-02-03", "2023-02-04"
                    )
                }
            )
            env = env.model_copy(
                update={
                    "snapshot_ref": put(
                        store, snapshot.model_copy(update={"request": changed})
                    )
                }
            )
        elif fault == "binding":
            changed = snapshot.request.model_copy(
                update={
                    "binding_ref": put(
                        store,
                        c["binding"].model_copy(
                            update={"baseline_ref": c["binding"].private_spec_ref}
                        ),
                    )
                }
            )
            env = env.model_copy(
                update={
                    "snapshot_ref": put(
                        store, snapshot.model_copy(update={"request": changed})
                    )
                }
            )
        elif fault == "recovery":
            site = c["c"].spec
            recovery = RecoveryPlan.model_validate_json(
                store.read(site.token.recovery_ref, control=guard())
            )
            config = site.configuration.model_copy(
                update={
                    "token": site.token.model_copy(
                        update={
                            "recovery_ref": put(
                                store,
                                recovery.model_copy(
                                    update={"state_coverage": ("incomplete",)}
                                ),
                            )
                        }
                    )
                }
            )
            env = env.model_copy(
                update={
                    "site_spec_ref": put(
                        store, site.model_copy(update={"configuration": config})
                    )
                }
            )
        else:
            state = snapshot.state
            service = state.service
            if fault == "image":
                service = service.model_copy(
                    update={
                        "files": service.files.model_copy(
                            update={
                                "image": service.files.image.model_copy(
                                    update={"sha256": "0" * 64}
                                )
                            }
                        )
                    }
                )
                state = state.model_copy(update={"service": service})
            elif fault == "ports":
                state = state.model_copy(
                    update={
                        "service": service.model_copy(
                            update={
                                "ports": service.ports.model_copy(update={"web": 15000})
                            }
                        )
                    }
                )
            else:
                stop = state.original_stop
                first = stop.namespaces[0]
                original = first.original
                original = original.model_copy(
                    update={
                        "launcher": original.launcher.model_copy(
                            update={"boot_id": "other"}
                        ),
                        "init": original.init.model_copy(update={"boot_id": "other"}),
                    }
                )
                state = state.model_copy(
                    update={
                        "original_stop": stop.model_copy(
                            update={
                                "namespaces": (
                                    first.model_copy(update={"original": original}),
                                    *stop.namespaces[1:],
                                )
                            }
                        )
                    }
                )
            env = env.model_copy(
                update={
                    "snapshot_ref": put(
                        store, snapshot.model_copy(update={"state": state})
                    )
                }
            )
        with pytest.raises((ValueError, OwnershipConflict)):
            c["checks"].environment(env, put(store, env), c["operation"], guard())


@pytest.mark.parametrize(
    "fault", ["closure", "restore", "resume", "intent", "protected"]
)
def test_reset_requires_every_original_closed_resource_and_native_fact(
    node_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with qualified(tmp_path, node_path, monkeypatch) as c:
        selection = c["reset"]
        store = c["store"]
        if fault == "closure":
            from lab_generate_skill.domain.lifecycle import ClosureReceipt

            closure = ClosureReceipt.model_validate_json(
                store.read(selection.closure_refs[0], control=guard())
            )
            selection = selection.model_copy(
                update={
                    "closure_refs": (
                        put(
                            store, closure.model_copy(update={"status": "unconfirmed"})
                        ),
                    )
                }
            )
        elif fault == "restore":
            result = SiteTaskResult.model_validate_json(
                store.read(selection.restore_result_ref, control=guard())
            )
            selection = selection.model_copy(
                update={
                    "restore_result_ref": put(
                        store, result.model_copy(update={"request_sha256": "0" * 64})
                    )
                }
            )
        elif fault in ("resume", "protected"):
            resume_result = SiteResumeResult.model_validate_json(
                store.read(selection.resume_result_ref, control=guard())
            )
            if fault == "resume":
                resume_result = resume_result.model_copy(
                    update={"request_sha256": "0" * 64}
                )
            else:
                observed = OrderEtaResumed.model_validate_json(
                    resume_result.private_result
                )
                observed = observed.model_copy(
                    update={
                        "protected": observed.protected.model_copy(
                            update={"core_fingerprint": "0" * 64}
                        )
                    }
                )
                resume_result = resume_result.model_copy(
                    update={"private_result": observed.model_dump_json()}
                )
            selection = selection.model_copy(
                update={"resume_result_ref": put(store, resume_result)}
            )
        else:
            from lab_generate_skill.domain.site_resume import SiteResumeIntent

            intent = SiteResumeIntent.model_validate_json(
                store.read(selection.resume_intent_ref, control=guard())
            )
            selection = selection.model_copy(
                update={
                    "resume_intent_ref": put(
                        store,
                        intent.model_copy(update={"configuration_sha256": "0" * 64}),
                    )
                }
            )
        with pytest.raises((ValueError, OwnershipConflict)):
            c["checks"].reset(selection, put(store, selection), guard())
