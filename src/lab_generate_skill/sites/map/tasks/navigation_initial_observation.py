"""Read persisted navigation capture against the original unique initial return."""

from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from ..navigation_initial_evidence import NavigationInitialReadiness
from ..navigation_initial_readiness_rules import original_navigation_readiness
from ..navigation_initial_rules import same_start_document
from .navigation_policy import navigation_initial_spec
from .initial_capture_records import MapInitialCaptureRecords


class NavigationInitialObservationChecks(MapInitialCaptureRecords):
    def __init__(
        self,
        store: EvidenceReader,
        evidence: MapInitialEvidence,
        initialization: MapNavigationInitialization,
    ) -> None:
        super().__init__(store, evidence)
        self.initialization = MapNavigationInitialization.model_validate(initialization)

    def check(
        self, inputs: InitialObservationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = InitialObservationInputs.model_validate(inputs)
        control.checkpoint()
        cfg = inputs.browser.configuration
        selected = cfg.initialization
        if (
            not isinstance(selected, MapNavigationInitialization)
            or selected != self.initialization
            or cfg.map_inputs is not None
        ):
            raise OwnershipConflict(
                "Original explicit navigation initialization required"
            )
        selected.check(cfg.spec)
        if (
            selected.prepared_ref != inputs.selection.preparation.prepared_ref
            or inputs.spec
            != navigation_initial_spec(
                inputs.prepared.scope.task, selected.native_contract_sha256
            )
        ):
            raise OwnershipConflict("Navigation initial preparation/coverage changed")
        intent, result = self._capture(inputs, ("map-navigation-initial", "1"), control)
        proof = NavigationInitialReadiness.model_validate_json(result.private_result)
        if (
            proof.model_dump_json() != result.private_result
            or proof.initialization != selected
        ):
            raise EvidenceIntegrityError(
                "Original navigation initial capture bytes/configuration changed"
            )
        original_navigation_readiness(proof, inputs.prepared.public_task)
        observed = inputs.observation.record
        returned = inputs.returned
        ready = (
            observed.state == "ready"
            and not observed.last_action_error
            and bool(inputs.observation.text)
            and len(observed.tabs) == 1
            and same_start_document(inputs.prepared.public_task, observed.tabs[0].url)
            and not (
                returned.terminated or returned.truncated or returned.protocol_terminal
            )
            and not any(
                e.kind in ("before_action", "after_action") for e in returned.events
            )
        )
        refs = (
            inputs.selection.browser_acquired_ref,
            inputs.acquired.details.started.initial_return_ref,
            self.evidence.intent_ref,
            self.evidence.result_ref,
        )
        control.checkpoint()
        return StateChecks(
            required=inputs.spec.initial_checks,
            checks=tuple(
                CheckResult(
                    name=name,
                    status="pass" if ready else "fail",
                    reason_code=(
                        "ORIGINAL_NAVIGATION_INITIAL_READY"
                        if ready
                        else "INITIAL_NAVIGATION_VIEW_NOT_READY"
                    ),
                    evidence=refs,
                )
                for name in inputs.spec.initial_checks
            ),
        )
