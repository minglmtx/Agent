"""Immutable task definitions with required site/split/baseline authorization.

A binding publication is not a source claim, PreparedTask or execution permit.
Each read/publication verifies actual dependency bytes and authority again.
"""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from lab_generate_skill.domain.task_publication import TaskBindingInputs
from .lifecycle import OperationControl


class TaskBindingAuthority(Protocol):
    """Verify registration/release, source/split/public-input permission and baseline.

    Verify private schema/semantics and actual baseline closure, including any
    transitive dependencies, for this caller/operation. No default approval; no
    initialization or restore may occur inside this read-only verification.
    """

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None: ...


class TaskBindings(Protocol):
    def publish(self, binding: TaskBinding, op: OperationContext) -> EvidenceRef: ...
    def load(self, reference: EvidenceRef, op: OperationContext) -> TaskBinding: ...


@runtime_checkable
class TaskBindingInputLoads(Protocol):
    """Optional same-call body output, preserving every original live check.

    Consumers check the capability flag first. A supervised whole-graph loader
    can retain its own existing fast path without extra per-leaf reads.
    """

    @property
    def loads_inputs_in_one_call(self) -> bool: ...

    def load_inputs(
        self, reference: EvidenceRef, op: OperationContext
    ) -> TaskBindingInputs: ...


class TaskBindingLoadChecks(Protocol):
    """Load all original immutable bytes and semantic authority on this call.

    The installed source reader may collapse transports, never caller/owner or
    reference integrity checks. No result remains valid for a later operation.
    """

    def load_binding(
        self, reference: EvidenceRef, op: OperationContext, control: OperationControl
    ) -> TaskBinding: ...


@runtime_checkable
class TaskBindingInputLoadChecks(TaskBindingLoadChecks, Protocol):
    """Optional bodies from this same supervised proof, with fresh live checks."""

    def load_binding_inputs(
        self, reference: EvidenceRef, op: OperationContext, control: OperationControl
    ) -> TaskBindingInputs: ...
