"""Dispatch only among explicitly frozen profiles on one original Actor worker.

This registry creates no process, request identity, retry or second ledger.
Read-only review cannot acquire the live measure capability.
"""

from copy import copy

from lab_generate_skill.domain.context_budget import (
    ContextBudgetProfile,
    CountedContextInput,
    TokenMeasurement,
)
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.evidence import EvidenceReader, EvidenceStore
from .context_tokens import ActorContextTokenCounter
from .context_count_review import ActorContextCountReviewer


class ActorContextCounters:
    def __init__(self, counters: dict[str, ActorContextTokenCounter]) -> None:
        if not counters:
            raise ValueError("Nonempty frozen Actor counters required")
        self._counters = dict(counters)

    def with_inputs(self, evidence: EvidenceStore) -> "ActorContextCounters":
        counters = {}
        for key, original in self._counters.items():
            counter = copy(original)
            counter._evidence = evidence
            counters[key] = counter
        return ActorContextCounters(counters)

    def measure(
        self,
        input_ref: EvidenceRef,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> CountedContextInput:
        profile = ContextBudgetProfile.model_validate(profile)
        control.checkpoint()
        if profile.digest not in self._counters:
            raise OwnershipConflict(
                "Actor count profile is not in original configuration"
            )
        return self._counters[profile.digest].measure(
            input_ref, profile, policy, control=control
        )

    def measure_with_return(
        self,
        input_ref: EvidenceRef,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
        retention_control: OperationControl,
    ) -> CountedContextInput:
        profile = ContextBudgetProfile.model_validate(profile)
        control.checkpoint()
        if profile.digest not in self._counters:
            raise OwnershipConflict(
                "Actor count profile is not in original configuration"
            )
        return self._counters[profile.digest].measure_with_return(
            input_ref,
            profile,
            policy,
            control=control,
            retention_control=retention_control,
        )


class ActorContextCountReviews:
    def __init__(self, reviewers: dict[str, ActorContextCountReviewer]) -> None:
        if not reviewers:
            raise ValueError("Nonempty frozen Actor count reviewers required")
        self._reviewers = dict(reviewers)

    def with_inputs(self, evidence: EvidenceReader) -> "ActorContextCountReviews":
        # The qualified native count verifier stays byte-for-byte unchanged.
        # Only this outer assembly supplies another reader for the same complete
        # immutable input graph; no successful verification result is copied.
        reviewers = {}
        for key, original in self._reviewers.items():
            reviewer = copy(original)
            reviewer._evidence = evidence
            reviewers[key] = reviewer
        return ActorContextCountReviews(reviewers)

    def verify(
        self,
        counted: CountedContextInput,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> TokenMeasurement:
        profile = ContextBudgetProfile.model_validate(profile)
        control.checkpoint()
        if profile.digest not in self._reviewers:
            raise OwnershipConflict(
                "Count review profile is not in original configuration"
            )
        return self._reviewers[profile.digest].verify(
            counted, profile, policy, control=control
        )
