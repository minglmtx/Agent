"""Recorded Actor execution capability; routing facts are never prompt content.

Implementations resolve and verify original public projection and parameters,
live model/resource/writer authority and storage limits. A paid implementation
must separately obtain the existing shared-ledger send permission; local calls
must not fabricate paid records. No default authority or retry is provided.
"""

from typing import Protocol
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.trace_events import GenerationIntent
from .lifecycle import OperationControl


class ActorModel(Protocol):
    def validate(self, intent: GenerationIntent, *, control: OperationControl) -> None:
        """Read-only preflight; no model call, reservation or new intent."""
        ...

    def generate(
        self, intent: GenerationIntent, *, control: OperationControl
    ) -> ActorGeneration:
        """Invoke once under live authority and preserve exact actual input/return.

        Called only after first trace-intent acknowledgement. Completed, failed
        and uncertain returns must describe actual attempted calls and retained
        response/diagnostic bytes. Unconfirmed execution raises with its original
        facts; the caller must not infer a not-sent outcome or resend. Independent
        bounded backend cleanup may persist a return after caller cancellation.
        """
        ...
