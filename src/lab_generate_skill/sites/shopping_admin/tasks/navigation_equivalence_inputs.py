"""Exact two measured Admin selections/snapshots for one owned comparison.

No read-through store, persistence, native action, or current permission. Each
comparison recomputes the original rule over the complete acknowledged bytes.
The task context authority owns lifetime and performs live checks separately.
"""

from dataclasses import dataclass
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.public_context import PublicContextInputs
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes


@dataclass(frozen=True)
class _NavigationComparisonEvidence:
    bodies: tuple[tuple[EvidenceRef, bytes], ...]

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        matching = [raw for ref, raw in self.bodies if ref == reference]
        if len(matching) != 1:
            raise OwnershipConflict("Comparison requested an unmeasured dependency")
        raw = matching[0]
        require_complete_bytes(reference, raw)
        control.checkpoint()
        return raw


@dataclass(frozen=True)
class NavigationComparisonInputs:
    source: PublicContextInputs
    candidate: BaselineInputs
    evidence: _NavigationComparisonEvidence

    @classmethod
    def read_original(
        cls,
        store: EvidenceReader,
        source: PublicContextInputs,
        candidate: BaselineInputs,
        control: OperationControl,
    ) -> "NavigationComparisonInputs":
        source = PublicContextInputs.model_validate(source)
        candidate = BaselineInputs.model_validate(candidate)
        bodies: dict[EvidenceRef, bytes] = {}
        for inputs in (source.baseline_inputs, candidate):
            references = {
                ref
                for check in inputs.environment.checks.checks
                for ref in check.evidence
                if ref.content_schema == "environment-selection/1"
            }
            if len(references) != 1:
                raise OwnershipConflict("One original environment selection required")
            reference = next(iter(references))
            control.checkpoint()
            raw = store.read(reference, control)
            require_complete_bytes(reference, raw)
            selection = EnvironmentSelection.model_validate_json(raw)
            bodies[reference] = raw
            control.checkpoint()
            snapshot = store.read(selection.snapshot_ref, control)
            require_complete_bytes(selection.snapshot_ref, snapshot)
            bodies[selection.snapshot_ref] = snapshot
        measured = cls(
            source, candidate, _NavigationComparisonEvidence(tuple(bodies.items()))
        )
        # This runs all existing scope, canonical-body, recovery, observation,
        # readiness and content-equivalence checks before the handoff exists.
        measured.compare(source, candidate, control)
        return measured

    def compare(
        self,
        source: PublicContextInputs,
        candidate: BaselineInputs,
        control: OperationControl,
    ) -> StateChecks:
        from .navigation_equivalence import NavigationInitialComparison

        control.checkpoint()
        if source != self.source or candidate != self.candidate:
            raise OwnershipConflict("Comparison changed original measured inputs")
        return NavigationInitialComparison(self.evidence).compare(
            source, candidate, control
        )
