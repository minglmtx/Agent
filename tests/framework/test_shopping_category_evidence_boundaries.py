"""Fixed proof boundaries and same-call bytes; no synthetic runtime grant."""

from collections import Counter
from typing import Any
import pytest
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.sites.shopping.navigation_evidence import (
    CategoryNavigationEvidence,
)
from lab_generate_skill.sites.shopping.navigation_evidence_bodies import (
    CategoryEvidenceBodies,
)
from lab_generate_skill.sites.shopping.navigation_evaluation_reads import (
    CategoryNavigationEvaluationReads,
)
from lab_generate_skill.evaluators.shopping.navigation import (
    CategoryNavigationEvaluator,
    REQUIREMENTS,
)
from test_shopping_category_navigation_input import originals as originals
from test_slurm_commands import guard


def ref(
    raw: bytes, schema: str = "shopping-category-navigation/1", producer: str = "unit"
) -> EvidenceRef:
    return evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer=producer,
        ),
    )


class Bytes:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.calls: Counter[EvidenceRef] = Counter()
        self.denied = False

    def read(self, reference: EvidenceRef, control: Any) -> bytes:
        control.checkpoint()
        self.calls[reference] += 1
        if self.denied:
            raise PermissionError("Original storage or dynamic gate revoked")
        return self.raw


def test_complete_refs_deduplicate_only_inside_one_call_and_closed_reader_refused() -> (
    None
):
    raw = b"{}"
    reference = ref(raw)
    original = Bytes(raw)
    bodies = CategoryEvidenceBodies(original)
    assert bodies.read(reference, guard()) == bodies.read(reference, guard()) == raw
    assert original.calls[reference] == 1
    alias = reference.model_copy(update={"producer": "other"})
    assert bodies.read(alias, guard()) == raw and original.calls[alias] == 1
    bodies.close()
    with pytest.raises(InvalidTransition):
        bodies.read(reference, guard())
    later = CategoryEvidenceBodies(original)
    assert later.read(reference, guard()) == raw and original.calls[reference] == 2
    later.close()


@pytest.mark.parametrize(
    "fault", ["claim", "large", "noncas", "wrongbytes", "cancel", "owner"]
)
def test_nonshared_dynamic_outside_scope_and_failed_bytes_keep_original_boundary(
    fault: str,
) -> None:
    raw = b"{}" if fault != "large" else b"a" * (1024**2 + 1)
    original = Bytes(raw)
    reference = ref(
        raw, "source-claim/1" if fault == "claim" else "shopping-category-navigation/1"
    )
    if fault == "noncas":
        reference = reference.model_copy(update={"uri": "engineering:nonpersistent"})
    if fault == "wrongbytes":
        original.raw = b"bad"
    bodies = CategoryEvidenceBodies(original)

    class Cancel:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "category-evidence-bodies")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    if fault == "wrongbytes":
        with pytest.raises(EvidenceIntegrityError):
            bodies.read(reference, guard())
        assert not bodies.bodies
    elif fault == "cancel":
        with pytest.raises(OperationStopped):
            bodies.read(reference, Cancel())
        assert not original.calls
    elif fault == "owner":
        bodies.owner = (-1, -1)
        with pytest.raises(InvalidTransition):
            bodies.read(reference, guard())
        assert not original.calls
    else:
        assert bodies.read(reference, guard()) == raw
        assert not bodies.bodies
        original.denied = True
        with pytest.raises(PermissionError):
            bodies.read(reference, guard())
        assert original.calls[reference] == 2
    bodies.close()


def missing() -> CategoryNavigationEvidence:
    return CategoryNavigationEvidence(
        environment_ref=None,
        initial=None,
        initial_checks_ref=None,
        trace_ref=None,
        trace_snapshot_ref=None,
        terminal_return_ref=None,
        page=None,
        final_guard=None,
        browser_closure_ref=None,
    )


def test_actual_loader_missing_facts_remain_unknown_before_any_storage(
    originals: Any,
) -> None:
    public = originals[0][2]

    class NoIO:
        def read(self, *args: Any, **kwargs: Any) -> bytes:
            raise AssertionError("Missing selected facts reached storage")

    def no_initial(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Missing initial facts reached loader")

    unavailable: Any = None
    selected = missing()
    loader = CategoryNavigationEvaluationReads(
        unavailable, unavailable, no_initial, no_initial
    )
    contract = EvaluationContract(
        identity=public.identity,
        attempt_id="attempt",
        task_contract_ref=ref(b"binding", "task-binding/1"),
        public_task_ref=ref(b"public", "public-task/1").model_copy(
            update={"visibility": "public"}
        ),
        completion_spec_ref=ref(b"private"),
        requirements=REQUIREMENTS,
        scope="engineering",
    )
    judgment = CategoryNavigationEvaluator(selected, loader).evaluate(
        contract, NoIO(), guard()
    )
    assert judgment.status == "unknown" and judgment.reward is None
    assert all(check.status == "unknown" for check in judgment.checks)


@pytest.mark.parametrize("value", [None, {}, [], "", False])
def test_invalid_selection_refused(value: Any) -> None:
    with pytest.raises(ValueError):
        CategoryNavigationEvidence.model_validate(value)
