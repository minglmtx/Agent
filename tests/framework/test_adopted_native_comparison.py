"""Actual concrete rules over complete synthetic CAS graphs; no runtime grants."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.domain.initial_adoption import (
    InitialAdoptionBinding,
    InitialAdoptionInputs,
)
from lab_generate_skill.domain.claims import SourceClaimReceipt
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.domain.public_context import assemble_public_context
from lab_generate_skill.domain.baseline import assemble_baseline
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.sites.shopping_admin.tasks.navigation_equivalence import (
    NavigationInitialComparison as AdminComparison,
)
from lab_generate_skill.sites.map.tasks.navigation_equivalence import (
    NavigationInitialComparison as MapComparison,
)
from current_initial_adoption_fixtures import current_initial_case
from admin_navigation_equivalence_fixtures import baseline, source
from evidence_control_fixtures import EvidenceFixtureStore
from preparation_record_fixtures import put
from task_initialization_port_fixtures import initialization_case
from task_initialization_source_fixtures import historical_source
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path
import state_contract_fixtures as states


def adoption_for(
    template: Any, original: Any, candidate: Any, store: Any
) -> tuple[InitialAdoptionInputs, Any]:
    """Typed unit provenance only; actual authority is intentionally absent."""
    run = template.run.model_copy(update={"owner": candidate.prepared.scope.owner})
    origin = template.frozen_origin
    old = origin.validation.parent.record
    old_run = old.binding.run.model_copy(
        update={"owner": original.baseline.scope.owner}
    )
    record = old.model_copy(
        update={
            "binding": old.binding.model_copy(
                update={"run": old_run, "task": candidate.binding}
            ),
            "operation": old.operation.model_copy(
                update={
                    "run_id": old_run.owner.run_id,
                    "owner_id": old_run.owner.owner_id,
                }
            ),
        }
    )
    parent = SourceClaimReceipt(record=record, reference=put(store, record))
    # The old comparison fixture's Reset was individually valid but its new
    # recovery refs had not been joined back into the complete source baseline.
    inputs = original.baseline_inputs
    task_ref = original.reset_inputs.plan.task_recovery_ref
    env_ref = original.reset_inputs.plan.environment_recovery_ref
    env = inputs.environment.model_copy(
        update={
            "allocation": inputs.environment.allocation.model_copy(
                update={"recovery_ref": env_ref}
            )
        }
    )
    env_body_ref = put(store, env)
    prep = inputs.preparation.model_copy(
        update={
            "environment_ref": env_body_ref,
            "recovery_ref": task_ref,
            "operation": inputs.preparation.operation.model_copy(
                update={"recovery_ref": task_ref}
            ),
        }
    )
    prep_ref = put(store, prep)
    prepared = inputs.prepared.model_copy(
        update={"preparation_ref": prep_ref, "recovery_ref": task_ref}
    )
    prepared_ref = put(store, prepared)
    initial = inputs.initial.model_copy(update={"prepared_ref": prepared_ref})
    repaired = inputs.model_copy(
        update={
            "environment": env,
            "environment_ref": env_body_ref,
            "preparation": prep,
            "preparation_ref": prep_ref,
            "prepared": prepared,
            "prepared_ref": prepared_ref,
            "initial": initial,
            "initial_ref": put(store, initial),
        }
    )
    baseline = assemble_baseline(repaired, original.baseline.operation)
    original = original.model_copy(
        update={
            "baseline_inputs": repaired,
            "baseline": baseline,
            "baseline_ref": put(store, baseline),
        }
    )
    publication = original.baseline.operation.model_copy(
        update={"operation_id": "unit-adopted-context", "attempt_id": None}
    )
    receipt = assemble_public_context(original, publication)
    context_ref = put(store, receipt)
    intent = template.intent.model_copy(
        update={
            "binding": template.intent.binding.model_copy(
                update={
                    "run": run,
                    "task": candidate.binding.identity,
                    "attempt_id": candidate.prepared.scope.attempt_id,
                }
            ),
            "public_context_ref": original.context_ref,
        }
    )
    selected = ExecutionTaskSource(
        schema_version="execution-task-source/2",
        run=run,
        task=candidate.binding,
        intent=intent,
        source_context_receipt_ref=context_ref,
        frozen_origin=origin.model_copy(
            update={
                "validation": origin.validation.model_copy(
                    update={"parent": parent, "target_release_ref": run.release_ref}
                )
            }
        ),
    )
    return (
        InitialAdoptionInputs(
            binding=InitialAdoptionBinding(
                scope=candidate.prepared.scope,
                binding=intent.binding,
                execution_source_ref=put(store, selected),
                source_context_ref=context_ref,
            ),
            source=selected,
        ),
        original,
    )


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Any:
    case = current_initial_case(tmp_path_factory.mktemp("adopted-template") / "case")
    assert case.inputs.adoption is not None
    return case.inputs.adoption.source


@pytest.fixture
def admin_pair(
    tmp_path: Path, contracts: Any, monkeypatch: pytest.MonkeyPatch, template: Any
) -> Any:
    (tmp_path / "cas").mkdir()
    store = EvidenceFixtureStore(tmp_path / "cas")
    original = source(baseline(tmp_path / "old", store, contracts), store)
    old_scope, old_op = states.scope, states.op
    owner = old_scope().owner.model_copy(
        update={
            "run_id": "current-admin-run",
            "owner_id": "current-admin-owner",
            "job_id": "current-admin-job",
        }
    )
    monkeypatch.setattr(
        states, "scope", lambda: old_scope().model_copy(update={"owner": owner})
    )

    def current_op(*args: Any, **kwargs: Any) -> Any:
        return old_op(*args, **kwargs).model_copy(
            update={"run_id": owner.run_id, "owner_id": owner.owner_id}
        )

    monkeypatch.setattr(states, "op", current_op)
    candidate = baseline(tmp_path / "new", store, contracts, candidate=True)
    adopted, original = adoption_for(template, original, candidate, store)
    return original, candidate, adopted, AdminComparison(store)


def test_admin_adopted_comparison_uses_complete_original_contents(
    admin_pair: Any,
) -> None:
    original, candidate, adopted, rule = admin_pair
    saved = original.model_dump_json()
    with pytest.raises(OwnershipConflict):
        rule.compare(original, candidate, guard())
    assert rule.compare_adopted(original, candidate, adopted, guard()).status == "pass"
    assert original.model_dump_json() == saved
    changed = candidate.model_copy(
        update={
            "environment": candidate.environment.model_copy(
                update={"measured_state_sha256": "0" * 64}
            )
        }
    )
    with pytest.raises(OwnershipConflict):
        rule.compare_adopted(original, changed, adopted, guard())


@pytest.mark.parametrize(
    "fault",
    ["scope", "parent_owner", "parent_task", "public", "candidate_task", "readiness"],
)
def test_admin_adoption_rejects_changed_provenance_or_readiness(
    admin_pair: Any, fault: str
) -> None:
    original, candidate, adopted, rule = admin_pair
    if fault == "scope":
        candidate = candidate.model_copy(
            update={
                "prepared": candidate.prepared.model_copy(
                    update={
                        "scope": candidate.prepared.scope.model_copy(
                            update={"context_id": "foreign"}
                        )
                    }
                )
            }
        )
    elif fault == "parent_owner":
        original = original.model_copy(
            update={
                "baseline": original.baseline.model_copy(
                    update={"scope": candidate.prepared.scope}
                )
            }
        )
    elif fault == "parent_task":
        original = original.model_copy(
            update={
                "baseline_inputs": original.baseline_inputs.model_copy(
                    update={
                        "binding": original.baseline_inputs.binding.model_copy(
                            update={"registration_id": "foreign"}
                        )
                    }
                )
            }
        )
    elif fault == "public":
        original = original.model_copy(
            update={
                "context_ref": original.context_ref.model_copy(
                    update={"sha256": "0" * 64}
                )
            }
        )
    elif fault == "candidate_task":
        candidate = candidate.model_copy(
            update={
                "binding": candidate.binding.model_copy(
                    update={"registration_id": "foreign"}
                )
            }
        )
    else:
        candidate = candidate.model_copy(
            update={
                "observation": candidate.observation.model_copy(
                    update={"state": "error"}
                )
            }
        )
    with pytest.raises((OwnershipConflict, ValueError)):
        rule.compare_adopted(original, candidate, adopted, guard())


def test_map_adopted_comparison_preserves_semantic_failure_and_ordinary_refusal(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    template: Any,
) -> None:
    with initialization_case(node_path, monkeypatch) as case:
        case.start()
        p = case.preparation
        c = p.original
        store = c.resource.evidence
        candidate = case.initialization.state.baseline_inputs
        assert candidate is not None
        foreign = c.scope.owner.model_copy(
            update={
                "run_id": "old-map-run",
                "owner_id": "old-map-owner",
                "job_id": "old-map-job",
            }
        )
        old_recovery = RecoveryPlan.model_validate_json(
            store.read(c.resource.spec.token.recovery_ref)
        )
        old_recovery = old_recovery.model_copy(update={"owner": foreign})
        token = c.resource.spec.token.model_copy(
            update={"owner": foreign, "recovery_ref": put(store, old_recovery)}
        )
        proxy: Any = SimpleNamespace(
            original=SimpleNamespace(
                scope=c.scope.model_copy(update={"owner": foreign}),
                worker=c.worker,
                resource=SimpleNamespace(
                    evidence=store,
                    spec=SimpleNamespace(token=token),
                ),
            ),
            source=p.source,
            plan=p.plan.model_copy(
                update={
                    "operation": p.plan.operation.model_copy(
                        update={"run_id": foreign.run_id, "owner_id": foreign.owner_id}
                    )
                }
            ),
            reset=p.reset.model_copy(
                update={
                    "attempt_allocations": tuple(
                        t.model_copy(update={"owner": foreign})
                        for t in p.reset.attempt_allocations
                    )
                }
            ),
        )
        original, _, _ = historical_source(proxy)
        adopted, original = adoption_for(template, original, candidate, store)
        old = original.model_dump_json()
        rule = MapComparison()
        with pytest.raises(OwnershipConflict):
            rule.compare(original, candidate, guard())
        assert (
            rule.compare_adopted(original, candidate, adopted, guard()).status == "pass"
        )
        changed = candidate.model_copy(
            update={
                "environment": candidate.environment.model_copy(
                    update={"measured_state_sha256": "f" * 64}
                )
            }
        )
        assert (
            rule.compare_adopted(original, changed, adopted, guard()).status == "fail"
        )
        assert original.model_dump_json() == old
