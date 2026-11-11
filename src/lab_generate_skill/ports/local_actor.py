"""Required original trace/resource/public-projection authority; never defaults."""

from typing import Literal, Protocol
from lab_generate_skill.domain.local_actor import LocalActorCall, LocalActorExecution
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from .lifecycle import OperationControl


class LocalActorAuthority(Protocol):
    def verify(
        self,
        call: LocalActorCall,
        prompt: ActorPrompt,
        parameters: LocalActorParameters,
        guard: ProcessOwnerGuard,
        phase: Literal["preflight", "dispatch"],
        control: OperationControl,
    ) -> None:
        """Verify original writer/release/acquired model, live claim/attempt,
        exact public projection and planned method/parameters. Preflight must
        have no new generation intent; dispatch requires the exact pending
        original trace intent. Verify binding root in trusted assembly. Neither
        parsed refs nor an old acquired fact grants current invocation rights.
        """
        ...

    def verify_return(
        self, execution: LocalActorExecution, control: OperationControl
    ) -> None:
        """Verify actual original provenance, allowing independent result cleanup.
        A closed resource cannot erase its actual return, but an invented or
        foreign exchange cannot gain provenance from matching hashes alone.
        """
        ...
