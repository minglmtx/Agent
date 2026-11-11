"""Join original preparation/site facts to mandatory browser resource authority.

Cleanup never depends on still-readable preparation or a still-acquired site.
No default policy, Actor permission, new Observation, or site-effect retry.
"""

from typing import Literal
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourceStarted,
    BrowserResourceAttempt,
)
from lab_generate_skill.domain.browser_step import BrowserStepClosed
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.browser_resources import BrowserResourceAuthority
from lab_generate_skill.ports.lifecycle import OperationControl


class PreparedBrowserAuthority:
    def __init__(
        self,
        spec: BrowserResourceSpec,
        binding: PreparedBrowserBinding,
        authority: BrowserResourceAuthority,
    ) -> None:
        self.spec = BrowserResourceSpec.model_validate(spec)
        self.binding, self.authority = binding, authority

    def _same(self, spec: BrowserResourceSpec) -> None:
        if spec != self.spec:
            raise OwnershipConflict("Prepared browser changed original resource")

    def authorize_start(
        self,
        spec: BrowserResourceSpec,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._same(spec)
        self.binding.verify(spec, operation, control)
        self.authority.authorize_start(spec, operation, control)

    def verify(
        self,
        spec: BrowserSessionSpec,
        phase: Literal["start", "step", "close"],
        action: BrowserAction | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if spec != self.spec.configuration.spec:
            raise OwnershipConflict("Prepared browser changed original session")
        self.spec.check_operation(
            operation, "cleanup" if phase == "close" else "execute"
        )
        if phase != "close":
            self.binding.verify(self.spec, operation, control)
        self.authority.verify(spec, phase, action, operation, control)

    def verify_started(
        self,
        spec: BrowserResourceSpec,
        started: BrowserResourceStarted,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._same(spec)
        prepared = self.binding.verify(spec, operation, control)
        reads = self.binding.reads
        returned = reads.parse(
            started.initial_return_ref,
            "browser-initial-return/1",
            BrowserReadout,
            control,
        )
        observed = reads.parse(
            started.initial_observation_ref,
            "observation/1",
            Observation,
            control,
            visibility="public",
        )
        if (
            returned.scope != prepared.scope
            or returned.operation != operation
            or returned.action is not None
            or returned.observation != observed
            or observed.sequence != 0
            or observed.state != "ready"
            or observed.last_action_error
        ):
            raise OwnershipConflict(
                "Initial browser return differs from prepared attempt"
            )
        self.authority.verify_started(spec, started, operation, control)

    def verify_closed(
        self,
        spec: BrowserResourceSpec,
        attempt: BrowserResourceAttempt,
        termination: ProcessTermination | None,
        step: BrowserStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        self._same(spec)
        self.spec.check_operation(operation, "cleanup")
        return self.authority.verify_closed(
            spec, attempt, termination, step, operation, control
        )
