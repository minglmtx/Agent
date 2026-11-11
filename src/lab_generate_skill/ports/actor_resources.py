"""Mandatory provider authority, independent of per-request inference admission.

Verify actual fixed release/installed Python+package, artifact/config, Slurm job,
writer/source/resource ownership and device allowance before any spawn. Compare
child identity against independent actual process/cgroup observations. Closure
requires the original resource tree to be stopped, not just a reaped PID. No
production default, fixture authority or parsed metadata grants these rights.
"""

from typing import Protocol
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import (
    ProcessTermination,
)
from lab_generate_skill.domain.actor_step import (
    ActorStepStarted,
    ActorStepClosed,
    ActorStepCleanup,
)
from lab_generate_skill.ports.lifecycle import OperationControl


class ActorResourceAuthority(Protocol):
    def authorize_start(
        self,
        spec: ActorResourceSpec,
        op: OperationContext,
        control: OperationControl,
    ) -> None: ...
    def verify_started(
        self,
        spec: ActorResourceSpec,
        started: ActorStepStarted,
        op: OperationContext,
        control: OperationControl,
    ) -> None: ...
    def verify_closed(
        self,
        spec: ActorResourceSpec,
        cleanup: ActorStepCleanup,
        termination: ProcessTermination,
        op: OperationContext,
        control: OperationControl,
    ) -> ActorStepClosed | None:
        """Own the single live closure observation and return its saved facts.

        The caller already tried physical close. Missing paths are not clean.
        None is only possible for confirmed no-start-attempt/not_started, never
        a fallback after unknown start. Do not reread a now-removed cgroup after
        another layer has already finished a valid closure observation.
        """
        ...
