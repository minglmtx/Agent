"""Exact Admin comparison bodies and original owned cleanup/source gates."""

from collections import Counter
from dataclasses import replace
import inspect
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.sites.shopping_admin.tasks.navigation_equivalence import (
    NavigationInitialComparison,
)
from admin_navigation_equivalence_fixtures import baseline, source
from evidence_control_fixtures import EvidenceFixtureStore
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs


@pytest.mark.parametrize("fault", ["none", "body", "candidate", "cancel"])
def test_admin_comparison_uses_exact_complete_measured_bodies(
    tmp_path: Path, contracts: Any, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    (tmp_path / "cas").mkdir()
    store = EvidenceFixtureStore(tmp_path / "cas")
    original = source(baseline(tmp_path / "source", store, contracts), store)
    candidate = baseline(tmp_path / "candidate", store, contracts, candidate=True)
    read = store.read
    calls = []

    def counted(reference: Any, *args: Any, **kwargs: Any) -> bytes:
        calls.append(reference)
        return read(reference, *args, **kwargs)

    monkeypatch.setattr(store, "read", counted)
    measured = NavigationInitialComparison(store).read_comparison(
        original, candidate, guard()
    )
    assert len(calls) == len(set(calls)) == 4
    if fault == "body":
        bodies = measured.evidence.bodies
        measured = replace(
            measured,
            evidence=replace(
                measured.evidence,
                bodies=((bodies[0][0], bodies[0][1] + b" "), *bodies[1:]),
            ),
        )
    elif fault == "candidate":
        candidate = candidate.model_copy(
            update={
                "observation": candidate.observation.model_copy(update={"sequence": 1})
            }
        )

    class Cancelled:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "original-comparison")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    if fault == "none":
        for _ in range(3):
            assert measured.compare(original, candidate, guard()).status == "pass"
    else:
        with pytest.raises(
            (EvidenceIntegrityError, OwnershipConflict, OperationStopped)
        ):
            measured.compare(
                original, candidate, Cancelled() if fault == "cancel" else guard()
            )
    assert len(calls) == 4


@pytest.mark.parametrize("fault", ["none", "body"])
def test_owned_finalization_reuses_only_original_confirmed_reference_bodies(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from lab_generate_skill.adapters.sites.task_finalization_authority import (
        OriginalTaskFinalizationAuthority,
    )
    from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed

    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed_task_source_inputs(c, r, monkeypatch)
        store = c.p.original.resource.evidence
        original_read = store.read
        original_verify = OriginalTaskFinalizationAuthority.verify
        reads: Counter[Any] = Counter()
        injected: list[EvidenceRef] = []

        def read(reference: Any, *args: Any, **kwargs: Any) -> bytes:
            if any(
                frame.function == "read"
                and Path(frame.filename).name == "task_finalization_authority.py"
                for frame in inspect.stack(context=0)
            ):
                reads[reference] += 1
            result = original_read(reference, *args, **kwargs)
            assert isinstance(result, bytes)
            return result

        def verify(self: Any, *args: Any, **kwargs: Any) -> None:
            held = r.inputs
            assert held is not None and held.active
            if fault == "body" and not injected and held.finalization is not None:
                _, bodies = held.finalization
                if bodies:
                    reference = next(iter(bodies))
                    bodies[reference] += b" "
                    injected.append(reference)
            original_verify(self, *args, **kwargs)

        monkeypatch.setattr(store, "read", read)
        monkeypatch.setattr(OriginalTaskFinalizationAuthority, "verify", verify)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
        else:
            with pytest.raises(TaskExecutionUnconfirmed):
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert injected and c.bundle.finalization.state.reset is None
        assert reads and max(reads.values()) == 1
        assert c.native.loader.session.calls == 1
        assert r.inputs is not None and not r.inputs.active
        assert r.inputs.finalization is None and r.inputs.comparison is None
