"""Retained producer bodies through both real plan consumers, without replay.

Only the current storage gate and new declaration writes are unit premises. No
old owner is reacquired; this cannot authorize a site, claim, Actor or recovery.
"""

from dataclasses import fields, replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from admin_production_task_plan import (
    AdminProductionBudgets,
    freeze_admin_execution_inputs,
)
from production_task_plan import (
    FrozenActorInputs,
    MapProductionBudgets,
    freeze_execution_inputs,
)
from production_inputs import OriginalDocuments
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.closed_source_protocol import decode_command
from lab_generate_skill.bootstrap.admin_navigation_source_publication import (
    PublishedAdminNavigationSource,
)
from lab_generate_skill.bootstrap.map_closed_source import ClosedMapSourceDeclarations
from lab_generate_skill.bootstrap.map_source_publication import (
    PublishedClosedMapQualification,
)
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.closed_source_read import (
    ClosedAdminNavigationReadMaterial,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from initialization_binding_retained_fixtures import retained_inputs, CASES, W
from test_resource_journal import NoCancellation


@pytest.fixture(scope="module", params=("Admin", "Map"))
def original(request: pytest.FixtureRequest) -> Any:
    return load_retained_source_case(request.param)


def load_retained_source_case(site: str, *, job: int | None = None) -> Any:
    retained = retained_inputs(site, job=job)
    package, default_job = CASES[site]
    job = default_job if job is None else job
    root = W / "experiments" / package / f"production-{job}"
    material = decode_command(
        (root / "source-read/last-request.json").read_bytes()
    ).material

    def read(ref: EvidenceRef) -> bytes:
        return (root / "evidence/blobs" / ref.sha256).read_bytes()

    run = RunPlan.model_validate_json(
        read(retained["plan"].intent.binding.run.plan_ref)
    )
    assert isinstance(run.workload, ExecutionWorkload)
    policy = EngineeringActorPolicy.model_validate_json(
        read(run.workload.execution_policy_ref)
    )
    return SimpleNamespace(
        site=site,
        evidence_root=root / "evidence",
        retained=retained,
        material=material,
        actor=ActorResourceSpec.model_validate_json(
            read(run.resources.configuration_ref)
        ),
        parameters=LocalActorParameters.model_validate_json(
            read(run.models[0].parameters_ref)
        ),
        actor_inputs=FrozenActorInputs(
            ActorContextConfiguration.model_validate_json(
                read(policy.actor_context_ref)
            ),
            policy.actor_context_ref,
            policy,
            run.models[0].parameters_ref,
            retained["plan"].skill_ref,
        ),
    )


def consumer_case(original: Any, fault: str = "none") -> Any:
    c = original
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    op = c.retained["plan"].read_operation.model_copy(
        update={
            "operation_id": "unit-source-body-plan",
            "deadline": clock.utcnow() + timedelta(seconds=120),
        }
    )
    gates: list[OperationContext] = []
    writes: list[EvidenceRef] = []

    class CurrentGate:
        def check_context_current(
            self, operation: OperationContext, control: OperationControl
        ) -> None:
            control.checkpoint()
            assert operation == op
            gates.append(operation)
            if fault == "revoked":
                raise PermissionError("Unit current source storage admission revoked")
            if fault == "cancelled":
                raise OperationStopped("CANCELLED", operation.operation_id)

    class Declarations:
        def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
            raise AssertionError("Final plan must consume the already verified body")

        def put(
            self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            control.checkpoint()
            ref = evidence_reference(data, metadata)
            writes.append(ref)
            return ref

    source: Any
    freeze: Any
    budgets: Any
    if c.site == "Admin":
        assert isinstance(c.material, ClosedAdminNavigationReadMaterial)
        source = PublishedAdminNavigationSource(
            c.material,
            c.retained["source"],
            cast(Any, CurrentGate()),
            c.retained["source_inputs"],
        )
        freeze, budgets = freeze_admin_execution_inputs, AdminProductionBudgets()
    else:
        declarations = ClosedMapSourceDeclarations(
            **{
                f.name: getattr(c.material, f.name)
                for f in fields(ClosedMapSourceDeclarations)
            }
        )
        source = PublishedClosedMapQualification(
            declarations,
            c.retained["source"],
            cast(Any, CurrentGate()),
            c.retained["source_inputs"],
        )
        freeze, budgets = freeze_execution_inputs, MapProductionBudgets()
    if fault == "missing":
        source = replace(source, inputs=cast(Any, None))
    elif fault == "binding":
        initial = source.inputs.baseline_inputs
        source = replace(
            source,
            inputs=source.inputs.model_copy(
                update={
                    "baseline_inputs": initial.model_copy(
                        update={
                            "binding": initial.binding.model_copy(
                                update={"registration_id": "foreign-binding"}
                            )
                        }
                    )
                }
            ),
        )
    elif fault in ("reference", "producer"):
        value = source.material if c.site == "Admin" else source.declarations
        ref = value.context_ref.model_copy(
            update=(
                {"sha256": "0" * 64}
                if fault == "reference"
                else {"producer": "foreign-publisher"}
            )
        )
        if c.site == "Admin":
            source = replace(
                source, material=value.model_copy(update={"context_ref": ref})
            )
        else:
            source = replace(source, declarations=replace(value, context_ref=ref))
    elif fault == "schema":
        initial = source.inputs.baseline_inputs
        source = replace(
            source,
            inputs=source.inputs.model_copy(
                update={
                    "baseline_inputs": initial.model_copy(
                        update={
                            "prepared": initial.prepared.model_copy(
                                update={"schema_version": "prepared-task/999"}
                            )
                        }
                    )
                }
            ),
        )

    def invoke() -> Any:
        return freeze(
            source,
            c.retained["declaration"].scope,
            c.actor,
            c.parameters,
            c.actor_inputs.parameters_ref,
            b"unused declaration argument",
            OriginalDocuments(Declarations(), controls),
            op,
            budgets,
            c.actor_inputs,
        )

    return SimpleNamespace(invoke=invoke, source=source, gates=gates, writes=writes)


def test_retained_bodies_reach_final_consumer_without_leaf_reads(original: Any) -> None:
    case = consumer_case(original)
    result = case.invoke()
    assert len(case.gates) == 1
    assert case.writes
    assert result.task == original.retained["source_inputs"].baseline_inputs.binding
    assert result.inputs.source_context_receipt_ref == original.material.context_ref
    assert (
        result.task_binding_ref
        == original.retained["source_inputs"].baseline_inputs.prepared.task_binding_ref
    )


@pytest.mark.parametrize(
    "fault", ("missing", "binding", "reference", "producer", "schema")
)
def test_mismatch_is_refused_before_plan_writes(original: Any, fault: str) -> None:
    case = consumer_case(original, fault)
    with pytest.raises((ValueError, EvidenceIntegrityError, OwnershipConflict)):
        case.invoke()
    assert len(case.gates) == 1 and not case.writes


@pytest.mark.parametrize("fault", ("revoked", "cancelled"))
def test_valid_bodies_do_not_inherit_current_permission(
    original: Any, fault: str
) -> None:
    case = consumer_case(original, fault)
    with pytest.raises(PermissionError if fault == "revoked" else OperationStopped):
        case.invoke()
    assert len(case.gates) == 1 and not case.writes
