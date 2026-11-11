"""Existing unique observation plus original persisted initial capture, no page I/O."""

import hashlib
from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.map_initial_capture import (
    MapInitialCapture,
    MapInitialEvidence,
)
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from ..initial_readiness_rules import original_readiness
from ..native_view_rules import original_document
from .overlay_policy import overlay_initial_spec

T = TypeVar("T", bound=Contract)


from .initial_capture_records import MapInitialCaptureRecords


class OverlayInitialObservationChecks(MapInitialCaptureRecords):
    def __init__(
        self,
        store: EvidenceReader,
        evidence: MapInitialEvidence,
        initialization: MapNativeInitialization,
    ) -> None:
        super().__init__(store, evidence)
        self.initialization = MapNativeInitialization.model_validate(initialization)

    def check(
        self, inputs: InitialObservationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = InitialObservationInputs.model_validate(inputs)
        control.checkpoint()
        config = inputs.browser.configuration
        selected = config.initialization
        if (
            not isinstance(selected, MapNativeInitialization)
            or selected != self.initialization
            or config.map_inputs is None
        ):
            raise OwnershipConflict(
                "Explicit original Map initialization/collection required"
            )
        selected.check(config.spec)
        if (
            selected.prepared_ref != inputs.selection.preparation.prepared_ref
            or inputs.spec != overlay_initial_spec(inputs.prepared.scope.task)
        ):
            raise OwnershipConflict("Original Map initial preparation/coverage changed")
        intent, result = self._capture(inputs, ("map-initial-readiness", "1"), control)
        request = intent.request
        returned = inputs.returned
        proof = MapInitialCapture.model_validate_json(result.private_result)
        if (
            proof.model_dump_json() != result.private_result
            or proof.plan != config.map_inputs.plan
            or (
                proof.collection_sha256 != config.map_inputs.collection.digest
                or proof.readout_sha256
                != hashlib.sha256(returned.model_dump_json().encode()).hexdigest()
                or proof.observation_sha256 != request.observation_sha256
                or config.map_inputs.collection.operation != returned.operation
            )
        ):
            raise OwnershipConflict(
                "Map initial proof changed original unique readout/file plan"
            )
        original_readiness(
            proof.readiness_json.encode(), selected, inputs.prepared.public_task
        )
        view = inputs.observation.record
        ready = (
            view.state == "ready"
            and not view.last_action_error
            and bool(inputs.observation.text)
            and len(view.tabs) == 1
            and original_document(inputs.prepared.public_task, view.tabs[0].url)
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
                        "ORIGINAL_MAP_INITIAL_READY"
                        if ready
                        else "INITIAL_MAP_VIEW_NOT_READY"
                    ),
                    evidence=refs,
                )
                for name in inputs.spec.initial_checks
            ),
        )
