"""Final admission/owner joins on existing unit qualified-source/claim premises.

The original admission already runs in owned_navigation_case. Here its retained
return is injected to check the new outer join, original run history and failure
retention without claiming twice or acquiring any resource.
"""

from pathlib import Path
from typing import Any
import pytest
import admin_production_admission as module
from admin_production_admission import admit_admin_production_member
from admin_production_task_plan import (
    AdminProductionBudgets,
    prepare_admin_execution_configuration,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.application.execution_task_phase_source import (
    ExecutionTaskPhaseSources,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_run_journal import CancelSwitch
from test_linux_cgroups import actual_slurm_execution
from production_inputs import OriginalDocuments
from admin_navigation_owned_fixtures import owned_navigation_case
from test_admin_production_task_plan import frozen_case
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path


@pytest.fixture
def case(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> Any:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, contracts)
    base = c.source.site
    operation = c.declarations.plan.read_operation.model_copy(
        update={"operation_id": "final-admin-admission"}
    )
    prepared = prepare_admin_execution_configuration(
        frozen_case(c),
        c.owned.resources.site.spec,
        c.owned.resources.site.operation,
        c.declarations.preparation.scope,
        OriginalDocuments(base.evidence, base.controls),
        operation,
        AdminProductionBudgets(task_seconds=180, metadata_cleanup_seconds=60),
        base.clock,
    )
    run_root = tmp_path / "final-admin-run"
    run_root.mkdir()
    reads = c.source.read_factory(base.evidence, operation)
    calls = []

    def retained(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        assert args[0] == prepared.frozen.run
        assert args[1] == prepared.frozen.binding
        assert args[2] == c.source.qualified.material
        return c.admitted

    monkeypatch.setattr(module, "admit_admin_navigation_execution_source", retained)
    # The retained helper has already registered another run in its guard registry.
    # This separate outer-controller unit premise uses fresh guards, never a new claim.
    guards = OperationGuards(base.clock, CancelSwitch())
    observed, accounting = actual_slurm_execution()
    assert observed == c.source.owner.execution
    accounting_ref = OriginalDocuments(base.evidence, guards).raw(
        accounting, "original-slurm-accounting/1", operation
    )
    kwargs = dict(
        source=c.source.qualified,
        prepared=prepared,
        execution=c.source.owner.execution,
        controller=c.source.owner.controller,
        operation=operation,
        run_root=run_root,
        claim_root=c.admitted.claims._root,
        claim_scope="unit-admin-navigation",
        accounting_ref=accounting_ref,
        evidence=base.evidence,
        controls=guards,
        clock=base.clock,
        source_reads=reads,
    )
    return c, kwargs, calls


def test_original_run_and_owner_consume_same_retained_source_without_native_effects(
    case: Any,
) -> None:
    c, kwargs, calls = case
    original = {f.name: f.read_bytes() for f in c.admitted.claims._root.glob("*.json")}
    result = admit_admin_production_member(**kwargs)
    assert len(calls) == 1
    assert result.admitted is c.admitted
    assert isinstance(result.owner.sources, ExecutionTaskPhaseSources)
    assert result.owner.sources.source is c.admitted.reader
    assert result.owner.task_plan == result.declarations.plan
    assert result.owner.claim_ref == c.admitted.claim.reference
    assert (
        result.declarations.preparation.snapshot_schema == "admin-navigation-recovery/1"
    )
    assert (
        result.owner.runs.read(kwargs["operation"]).project()[0].events[-1].stage
        == "running"
    )
    assert c.owned.resources.site.phase == "new"
    assert original == {
        f.name: f.read_bytes() for f in c.admitted.claims._root.glob("*.json")
    }


@pytest.mark.parametrize("fault", ["source", "attempt", "owner", "run-root"])
def test_invalid_join_never_calls_original_admission(case: Any, fault: str) -> None:
    c, kwargs, calls = case
    if fault == "source":
        kwargs["source"] = None
    elif fault == "owner":
        kwargs["operation"] = kwargs["operation"].model_copy(
            update={"owner_id": "foreign"}
        )
    elif fault == "attempt":
        from dataclasses import replace

        p = kwargs["prepared"]
        f = p.frozen
        kwargs["prepared"] = replace(
            p,
            frozen=replace(
                f, inputs=f.inputs.model_copy(update={"attempt_id": "foreign"})
            ),
        )
    else:
        kwargs["run_root"] = kwargs["run_root"] / "absent"
    with pytest.raises((TypeError, ValueError, FileNotFoundError, OwnershipConflict)):
        admit_admin_production_member(**kwargs)
    assert calls == []
    assert c.owned.resources.site.phase == "new"


def test_postclaim_run_failure_retains_original_admitted_source_and_claim(
    case: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, kwargs, calls = case
    original = {f.name: f.read_bytes() for f in c.admitted.claims._root.glob("*.json")}

    def failure(*args: Any, **kw: Any) -> None:
        raise OSError("Original run history persistence failed")

    monkeypatch.setattr(module, "record_original_running_allocation", failure)
    with pytest.raises(OSError, match="run history") as caught:
        admit_admin_production_member(**kwargs)
    assert len(calls) == 1
    assert getattr(caught.value, "admin_original_admitted_source") is c.admitted
    assert original == {
        f.name: f.read_bytes() for f in c.admitted.claims._root.glob("*.json")
    }
    assert c.owned.resources.site.phase == "new"


@pytest.mark.parametrize("mode", ["execute", "cleanup"])
def test_task_source_reuses_only_its_same_call_validation(
    case: Any, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    c, kwargs, _ = case
    owner = c.owned.resources.owner
    parent = c.declarations.plan.read_operation
    operation = (
        parent.cleanup(
            "unit-single-source-cleanup", now=c.source.site.clock.utcnow(), seconds=60
        )
        if mode == "cleanup"
        else parent.model_copy(update={"operation_id": "unit-single-source-execute"})
    )
    reads = []
    original = owner.sources.read

    def count(*args: Any, **kw: Any) -> Any:
        reads.append(args)
        return original(*args, **kw)

    monkeypatch.setattr(owner.sources, "read", count)
    control = c.source.site.controls.bind(operation)
    first = owner.task_source(operation, control)
    assert len(reads) == 1
    assert owner.task_source(operation, control) == first
    assert len(reads) == 2

    # A subsequent call still checks the original durable claim and caller.
    def deny(*args: Any, **kw: Any) -> None:
        raise OwnershipConflict("original claim revoked")

    monkeypatch.setattr(owner.claims, "require_source", deny)
    with pytest.raises(OwnershipConflict, match="claim revoked"):
        owner.task_source(operation, control)
    assert len(reads) == 2


@pytest.mark.parametrize(
    "fault", ["missing-reply", "missing-ref", "wrong-task", "caller-revoked"]
)
def test_task_reference_reply_and_postread_caller_are_required(
    case: Any, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from types import SimpleNamespace
    from typing import cast
    from lab_generate_skill.adapters.plans.closed_source_records import (
        SupervisedSourceTaskBindingAuthority,
    )

    c, kwargs, _ = case
    checks = c.admitted.bindings.load_checks
    assert isinstance(checks, SupervisedSourceTaskBindingAuthority)
    reference = frozen_case(c).inputs.task_binding_ref
    from lab_generate_skill.adapters.plans.closed_source_protocol import (
        ClosedSourceBindingBodies,
    )

    binding = checks.owner.task
    store = c.source.site.evidence
    control = c.source.site.controls.bind(kwargs["operation"])
    bodies = ClosedSourceBindingBodies(
        binding=binding,
        public_task_json=store.read(binding.public_task_ref, control).decode(),
        private_spec_json=store.read(binding.private_spec_ref, control).decode(),
        baseline_json=store.read(binding.baseline_ref, control).decode(),
    )
    calls = []

    def corrupt(*args: Any, **kw: Any) -> Any:
        calls.append(kw)
        reply: Any = SimpleNamespace(
            binding=checks.owner.task,
            binding_reference=reference,
            binding_bodies=bodies,
        )
        if fault == "missing-reply":
            reply = None
        elif fault == "missing-ref":
            reply.binding_reference = None
        elif fault == "wrong-task":
            reply.binding = checks.owner.task.model_copy(
                update={
                    "identity": checks.owner.task.identity.model_copy(
                        update={"task_id": "foreign"}
                    )
                }
            )
        checks.transport.last_reply = cast(Any, reply)
        return c.source.qualified.receipt

    monkeypatch.setattr(checks.transport, "read", corrupt)
    if fault == "caller-revoked":
        original = checks.owner.require_caller
        owners = []

        def caller(operation: Any) -> None:
            owners.append(operation)
            original(operation)
            if len(owners) == 2:
                raise OwnershipConflict("caller revoked after read")

        monkeypatch.setattr(checks.owner, "require_caller", caller)
    with pytest.raises(OwnershipConflict):
        c.admitted.bindings.load(reference, kwargs["operation"])
    assert len(calls) == 1 and c.owned.resources.site.phase == "new"


@pytest.mark.parametrize("mode", ["execute", "cleanup"])
def test_same_call_source_supplies_full_run_once_and_next_call_rechecks(
    case: Any, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    from lab_generate_skill.adapters.plans.execution_task_source import (
        OriginalExecutionTaskSource,
    )

    c, _, _ = case
    owner = c.owned.resources.owner
    sources = owner.sources
    assert isinstance(sources, ExecutionTaskPhaseSources)
    assert isinstance(sources.source, OriginalExecutionTaskSource)
    assert sources.source.plans is owner.plans
    owner.source_run_reads = sources
    parent = c.declarations.plan.read_operation
    op = (
        parent
        if mode == "execute"
        else parent.cleanup(
            "same-call-run-cleanup", now=c.source.site.clock.utcnow(), seconds=60
        )
    )
    control = c.source.site.controls.bind(op)
    assert sources.source.source_checks is not None
    original = owner.plans.load
    original_source_load = sources.source.load
    proof_calls = []

    def source_load(*a: Any, **kw: Any) -> Any:
        proof_calls.append(a)
        return original_source_load(*a, **kw)

    monkeypatch.setattr(sources.source, "load", source_load)
    loads = []

    def load(*a: Any, **kw: Any) -> Any:
        loads.append(a)
        return original(*a, **kw)

    monkeypatch.setattr(owner.plans, "load", load)
    first = owner.task_source(op, control)
    assert len(loads) == 0 and len(proof_calls) == 1
    assert owner.task_source(op, control) == first
    assert len(loads) == 0 and len(proof_calls) == 2

    def deny(*a: Any, **kw: Any) -> None:
        raise OwnershipConflict("original caller revoked between source calls")

    monkeypatch.setattr(owner.authority, "require_caller", deny)
    with pytest.raises(OwnershipConflict, match="caller revoked"):
        owner.task_source(op, control)
    assert len(loads) == 0 and len(proof_calls) == 2


def test_source_returned_run_must_retain_full_original_binding(
    case: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _, _ = case
    owner = c.owned.resources.owner
    sources = owner.sources
    assert isinstance(sources, ExecutionTaskPhaseSources)
    owner.source_run_reads = sources
    original = sources.read_ownership

    def changed(*a: Any, **kw: Any) -> Any:
        value = original(*a, **kw)
        assert value is not None
        state, run, claim = value
        return (
            state,
            run.model_copy(
                update={
                    "resources": run.resources.model_copy(
                        update={
                            "cleanup_timeout_seconds": run.resources.cleanup_timeout_seconds
                            + 1
                        }
                    )
                }
            ),
            claim,
        )

    monkeypatch.setattr(sources, "read_ownership", changed)
    op = c.declarations.plan.read_operation
    from lab_generate_skill.domain.errors import EvidenceIntegrityError

    with pytest.raises(EvidenceIntegrityError, match="original bytes"):
        owner.task_source(op, c.source.site.controls.bind(op))
    assert c.owned.resources.site.phase == "new"
