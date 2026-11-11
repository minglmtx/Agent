"""Independent original recorded provenance and actual review runtime rights."""

from typing import Protocol
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.review import ReviewPlan
from lab_generate_skill.domain.run_plan import RunPlan
from .lifecycle import OperationControl


class ConstructionHistoryVerifier(Protocol):
    def verify(
        self,
        progress: ConstructionProgress,
        plan: ReviewPlan,
        control: OperationControl,
    ) -> None:
        """Check original source/context/retrieval, all calls and full native results.
        Read recorded facts only; no dispatch, live writer takeover or repair.
        """
        ...

    def verify_current(
        self,
        progress: ConstructionProgress,
        plan: ReviewPlan,
        control: OperationControl,
    ) -> None:
        """Match the original persisted construction, without replay or writes."""
        ...


class ReviewAuthority(Protocol):
    def verify(
        self,
        plan: ReviewPlan,
        original: RunPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Actual fixed review release/source/read rights; no default allow or
        training eligibility. Data refs alone never prove loaded implementation.
        """
        ...
