"""Publish actual browser facts and implement the shared BrowserActions port.

The raw readout survives publication failure. No persistence error triggers
another physical start/step. The returned StepResult binds the original action,
operation and previous observation; event/raw-return evidence stays private.
This adapter is a composition primitive, not an approved resource launcher.
"""

from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.browser_session import RawBrowserSession
from lab_generate_skill.ports.browser_viewport import BrowserViewportSource
from lab_generate_skill.domain.observation_viewport import (
    viewport_reference,
    VIEWPORT_METADATA,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from .return_publication import BrowserReturnPublication
from .published_step_inputs import PublishedStepInputs
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody


class EvidenceBrowserSession:
    def __init__(
        self,
        engine: RawBrowserSession,
        store: EvidenceStore,
        *,
        return_publication: BrowserReturnPublication | None = None,
        viewport_source: BrowserViewportSource | None = None,
    ) -> None:
        self.engine, self.store = engine, store
        self.return_publication = return_publication
        self.viewport_source = viewport_source
        self.observation_ref: EvidenceRef | None = None
        self.last_return_ref: EvidenceRef | None = None
        self.observation_body: VerifiedEvidenceBody | None = None
        self.published_step: PublishedStepInputs | None = None
        # Set only by registered_browser after actual initial-return admission.
        self.resource_started_ref: EvidenceRef | None = None

    def _publish(
        self, readout: BrowserReadout, control: OperationControl
    ) -> EvidenceRef:
        reference = viewport_reference(readout.observation)
        viewport = (
            None if self.viewport_source is None else self.viewport_source.viewport
        )
        if reference is not None:
            if viewport is None:
                raise EvidenceIntegrityError(
                    "Captured viewport body is missing; no recapture fallback"
                )
            viewport.require_observation(readout.observation)
            returned = self.store.put(
                viewport.model_dump_json().encode(), VIEWPORT_METADATA, control=control
            )
            if returned != reference:
                raise EvidenceIntegrityError(
                    "Viewport publication changed its complete artifact identity"
                )
        elif viewport is not None:
            raise EvidenceIntegrityError(
                "Stale viewport cannot accompany a legacy observation"
            )
        return self.store.put(
            readout.observation.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="observation/1",
                visibility="public",
                producer="browsergym-session-v1",
            ),
            control=control,
        )

    def start(
        self, operation: OperationContext, *, control: OperationControl
    ) -> EvidenceRef:
        if self.observation_ref is not None:
            raise InvalidTransition("Browser initial observation already published")
        try:
            result = self.engine.start(operation, control=control)
            self.last_return_ref = self.store.put(
                result.model_dump_json().encode(),
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema="browser-initial-return/1",
                    visibility="private",
                    producer="browsergym-session-v1",
                ),
                control=control,
            )
            self.observation_ref = self._publish(result, control)
            if self.return_publication is not None:
                self.observation_body = VerifiedEvidenceBody(
                    self.observation_ref, result.observation.model_dump_json().encode()
                )
            return self.observation_ref
        except BaseException:
            self.engine.quarantine()
            raise

    def step(
        self,
        action: BrowserAction,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> StepResult:
        before = self.observation_ref
        if before is None:
            raise InvalidTransition(
                "Publish initial browser observation before actions"
            )
        if self.engine.state != "ready":
            raise InvalidTransition(
                "Browser is not ready; retain prior return evidence"
            )
        self.last_return_ref = None
        self.published_step = None
        try:
            result = self.engine.step(action, operation, control=control)
            # Execution still uses the exact original action control. Only
            # already returned bytes use the selected independent result window.
            publication_control = (
                control
                if self.return_publication is None
                else self.return_publication.bind(operation)
            )
            self.last_return_ref = self.store.put(
                result.model_dump_json().encode(),
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema="browser-step-return/1",
                    visibility="private",
                    producer="browsergym-session-v1",
                ),
                control=publication_control,
            )
            observed = self._publish(result, publication_control)
            returned = StepResult(
                scope=self.engine.spec.scope,
                operation=operation,
                action_id=action.action_id,
                before_observation_ref=before,
                observation_ref=observed,
                return_ref=self.last_return_ref,
                terminal=result.terminated
                or result.truncated
                or result.protocol_terminal,
            )
            self.observation_ref = observed
            if (
                self.return_publication is not None
                and self.observation_body is not None
            ):
                if self.observation_body.reference != before:
                    raise InvalidTransition(
                        "Original previous observation body required"
                    )
                current = VerifiedEvidenceBody(
                    observed, result.observation.model_dump_json().encode()
                )
                self.published_step = PublishedStepInputs(
                    returned,
                    (
                        self.observation_body,
                        VerifiedEvidenceBody(
                            self.last_return_ref, result.model_dump_json().encode()
                        ),
                        current,
                    ),
                    self.store,
                )
                self.observation_body = current
            return returned
        except BaseException:
            self.engine.quarantine()
            raise

    def close(self, operation: OperationContext, *, control: OperationControl) -> None:
        try:
            self.engine.close(operation, control=control)
        finally:
            self.published_step = None
            self.observation_body = None
