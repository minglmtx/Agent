"""Augment original site admission with complete browser evidence verification."""

from collections.abc import Callable
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_capture import SiteCaptureAuthority
from lab_generate_skill.sites.map.terminal_evidence import TerminalMapEvidence
from lab_generate_skill.sites.map.reference_selection import (
    read_reference_selection,
    verify_reference_selection,
)


class MapReferenceAuthority:
    def __init__(
        self,
        original: SiteCaptureAuthority,
        store: EvidenceReader,
        terminal: Callable[[EvidenceRef, OperationControl], TerminalMapEvidence],
    ) -> None:
        self.original, self.store, self.terminal = original, store, terminal
        self.attempted: set[tuple[str, int]] = set()

    def verify_capture(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        request = SiteCaptureRequest.model_validate(request)
        request.check_site(configuration)
        if request.selection_ref is None or (
            request.collector_id,
            request.collector_version,
        ) != ("map-native-reference", "1"):
            raise ValueError("Only selected native Map reference uses this authority")
        self.original.verify_capture(configuration, request, intent_ref, control)
        selected = read_reference_selection(
            self.store, request.selection_ref, request.inspection, control
        )
        if selected.original_request_key in self.attempted:
            raise InvalidTransition(
                "Original Map request already admitted; unknown cannot be redispatched"
            )
        terminal = self.terminal(selected.terminal_selection_ref, control)
        verify_reference_selection(
            selected, terminal, request.inspection, self.store, control
        )
        control.checkpoint()
        self.attempted.add(selected.original_request_key)
