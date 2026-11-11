"""Dispatch exactly once after durable intent acknowledgement, then record facts.

Inputs: BrowserDispatch, existing TraceJournal and authorized browser capability,
plus controls. Output: confirmed trace snapshot containing the original return.
No site-specific branch, action parser, file I/O, model call or automatic retry.
The caller must already own the initialized session and live claim/resources.

Result recording uses the explicitly independent bounded cleanup command; a
cancelled action control does not erase a return already obtained. On failure,
the typed exception retains phase, original error, acknowledged intent and any
actual return/observed event. Reconcile the retained event through TraceJournal
with a new cleanup command; never call this dispatcher to recover a pending
intent. Session closure and persistent isolation are the surrounding lifecycle's
responsibility even when this operation or result persistence fails.
"""

from typing import Literal
from lab_generate_skill.domain.browser import StepResult
from lab_generate_skill.domain.browser_dispatch import BrowserDispatch
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.interaction import InteractionEvent
from lab_generate_skill.domain.trace_events import InteractionObserved
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.browser import BrowserActions
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.trace_journal import TraceJournal

Phase = Literal[
    "commit_intent", "before_step", "step", "validate_return", "commit_result"
]


class BrowserDispatchFailure(RuntimeError):
    reason_code = "BROWSER_DISPATCH_UNCONFIRMED"

    def __init__(
        self,
        request: BrowserDispatch,
        phase: Phase,
        primary: BaseException,
        acknowledged: TraceSnapshot | None,
        returned: object,
        observed: InteractionObserved | None,
    ) -> None:
        self.request, self.phase, self.primary = request, phase, primary
        self.acknowledged, self.returned, self.observed = (
            acknowledged,
            returned,
            observed,
        )
        super().__init__(
            f"Browser action stopped in {phase}; preserve original intent and do not redispatch"
        )


def execute_browser_action(
    request: BrowserDispatch,
    journal: TraceJournal,
    browser: BrowserActions,
    controls: OperationControls,
) -> TraceSnapshot:
    request = BrowserDispatch.model_validate(request)
    intent = request.intent
    action = intent.decision.action
    assert action is not None  # validated public boundary
    phase: Phase = "commit_intent"
    acknowledged: TraceSnapshot | None = None
    returned: object = None
    observed: InteractionObserved | None = None
    try:
        control = controls.bind(intent.execution_operation)
        control.checkpoint()
        acknowledged = TraceSnapshot.model_validate(
            journal.append(intent, request.expected_revision, intent.operation)
        )
        view = acknowledged.project()
        if (
            acknowledged.revision != request.expected_revision + 1
            or acknowledged.events[-1] != intent
            or view.action != intent
            or view.generation is None
        ):
            raise OwnershipConflict(
                "Journal did not acknowledge this exact first action intent"
            )
        phase = "before_step"
        control.checkpoint()
        phase = "step"
        returned = browser.step(action, intent.execution_operation, control=control)
        phase = "validate_return"
        result = StepResult.model_validate(returned)
        observed = InteractionObserved(
            operation=request.result_operation,
            interaction=InteractionEvent(
                scope=acknowledged.plan.scope,
                operation=intent.execution_operation,
                generation_id=intent.decision.generation_id,
                action=action,
                before_observation_ref=view.generation.before_observation_ref,
                outcome="returned",
                result=result,
            ),
        )
        # A return is a fact even if the action deadline/cancellation has fired.
        # Only the separate result command controls its bounded persistence.
        phase = "commit_result"
        after = TraceSnapshot.model_validate(
            journal.append(observed, acknowledged.revision, request.result_operation)
        )
        if (
            after.plan != acknowledged.plan
            or after.creation_operation != acknowledged.creation_operation
            or after.events != (*acknowledged.events, observed)
        ):
            raise OwnershipConflict(
                "Journal did not confirm the original browser return"
            )
        return after
    except BaseException as error:
        raise BrowserDispatchFailure(
            request, phase, error, acknowledged, returned, observed
        ) from error
