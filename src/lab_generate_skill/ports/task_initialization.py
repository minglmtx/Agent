"""Initial measurement and actual comparison over the existing state contracts."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.initial_observation_publication import (
    PublishedInitialObservation,
)
from lab_generate_skill.domain.initialization_admission_inputs import (
    InitializationAdmissionInputs,
)
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.public_context import PublicContextInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from .lifecycle import OperationControl
from lab_generate_skill.domain.initial_adoption import InitialAdoptionInputs


class TaskInitialMeasurements(Protocol):
    def record(
        self, selection: InitialObservationSelection, control: OperationControl
    ) -> EvidenceRef:
        """Original passive capture/checks; no new observation or Actor action."""
        ...


@runtime_checkable
class TaskInitialMeasurementReads(Protocol):
    def record_complete(
        self, selection: InitialObservationSelection, control: OperationControl
    ) -> PublishedInitialObservation:
        """One original capture/publication with confirmed bytes, never permission."""
        ...


class TaskInitialComparison(Protocol):
    def compare(
        self,
        source: PublicContextInputs,
        candidate: BaselineInputs,
        control: OperationControl,
    ) -> StateChecks:
        """Actual declared equivalence evidence; no source/candidate effects."""
        ...


@runtime_checkable
class TaskAdoptedInitialComparison(Protocol):
    def compare_adopted(
        self,
        source: PublicContextInputs,
        candidate: BaselineInputs,
        adoption: InitialAdoptionInputs,
        control: OperationControl,
    ) -> StateChecks:
        """Exact old/current provenance with original complete comparison rules."""
        ...


@runtime_checkable
class TaskInitialComparisonReads(Protocol):
    def read_comparison(
        self,
        source: PublicContextInputs,
        candidate: BaselineInputs,
        control: OperationControl,
    ) -> TaskInitialComparison:
        """Read exact immutable comparison inputs, without granting admission.

        The returned comparison must reject different source/candidate inputs
        and recheck their complete body identities. The owned task still checks
        current source/resource rights before every use.
        """
        ...


class TaskInitializationAuthority(Protocol):
    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskInitializationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Exact live starting intent/claim, original source and resource plans.

        Typed settings are not permission. Require real model/browser allocation,
        frozen method/context/parameters and exclusive physical/source authority.
        Cleanup reads do not grant another browser/capture dispatch.
        """
        ...


@runtime_checkable
class TaskInitializationBodyAuthority(Protocol):
    def verify_with_inputs(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskInitializationPlan,
        inputs: InitializationAdmissionInputs,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Consume same-call bodies; all live admission gates remain mandatory."""
        ...
