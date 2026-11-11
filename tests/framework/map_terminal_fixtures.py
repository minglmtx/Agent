"""Original registered graph and complete files; synthetic native/Page/kernel effects."""

from contextlib import contextmanager
from collections.abc import Iterator, Callable
from dataclasses import dataclass
from pathlib import Path
import hashlib
import traceback
import pytest
from lab_generate_skill.adapters.browsergym.worker_client import BrowserWorkerFailure
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.map_terminal_evidence import MapTerminalSelection
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.bootstrap.map_terminal_evidence import map_terminal_evidence
from lab_generate_skill.sites.map.terminal_evidence import TerminalMapEvidence
from map_registered_worker_fixtures import RegisteredMapCase
from map_initial_records_fixtures import initial, InitialCase
from preparation_record_fixtures import put
from test_map_browser_collection import capture
from test_slurm_commands import guard

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
PROOF = (
    W
    / "archives/legacy-project-reference-library-20261026-v1/records/95ca64fc4c3d113d183b3ec01fe65511f2c556633b8c35e4aa0ea8f6208209ea/b9101b71aacd51b61f6e.json"
)
CONTRACT = (
    W
    / "experiments/sft-map-original-layer-v1/prepared/contracts/b9101b71aacd51b61f6e.json"
)


@dataclass
class TerminalCase:
    original: RegisteredMapCase
    initial: InitialCase
    selection: MapTerminalSelection
    reference: EvidenceRef
    operation: OperationContext

    def load(
        self, selection: MapTerminalSelection | None = None
    ) -> TerminalMapEvidence:
        b = self.initial.browser
        browser_participant = b.participant
        original_observer = self.original.observer
        self.original.observer = "controller"
        b.participant = "controller"
        try:
            return map_terminal_evidence(
                b.resource.evidence,
                b.resource.controls,
                self.initial.preparation.records,
                (
                    put(b.resource.evidence, selection)
                    if selection is not None
                    else self.reference
                ),
                self.operation,
            )
        finally:
            b.participant = browser_participant
            self.original.observer = original_observer


@contextmanager
def terminal(
    c: RegisteredMapCase,
    patch: pytest.MonkeyPatch,
    *,
    action: str = "none",
    before_action: Callable[[InitialCase], None] | None = None,
    before_capture: Callable[[InitialCase], None] | None = None,
) -> Iterator[TerminalCase]:
    proof = select_original(c)
    with initial(c, patch) as i:
        b = i.browser
        if before_action is not None:
            before_action(i)
        if action != "none":
            name = "send_msg_to_user" if action == "protocol" else "click"
            payload = (
                "send_msg_to_user('done')" if action == "protocol" else "click('a')"
            )
            i.session.step(
                BrowserAction(
                    action_id="terminal-action",
                    protocol_id="browsergym-highlevel-v1",
                    name=name,
                    payload=payload,
                ),
                b.resource.op.model_copy(update={"operation_id": "last-action"}),
                control=guard(),
            )
        if before_capture is not None:
            before_capture(i)
        recorder, request = capture(b, i.session)
        try:
            result = recorder.capture(request, control=guard(30))
        except BrowserWorkerFailure as error:
            # Keep the remote exception/traceback visible in retained pytest logs.
            print(error.reply.model_dump_json())
            if b.collector is not None and b.collector.native is not None:
                for original_error in b.collector.native.requests.errors:
                    traceback.print_exception(original_error)
            raise
        assert recorder.intent_ref is not None
        selection = MapTerminalSelection(
            initial=i.selection,
            capture_intent_ref=recorder.intent_ref,
            capture_result_ref=result,
            original_reference_ref=proof,
        )
        yield TerminalCase(
            c,
            i,
            selection,
            put(b.resource.evidence, selection),
            i.operation.model_copy(update={"operation_id": "read-terminal"}),
        )


def select_original(c: RegisteredMapCase) -> EvidenceRef:
    ref = c.put(CONTRACT.read_bytes(), "map-native-contract/1")
    c.private = c.private.model_copy(update={"native_contract_ref": ref})
    inputs = c.configuration.map_inputs
    assert inputs is not None
    c.configuration = c.configuration.model_copy(
        update={
            "map_inputs": inputs.model_copy(
                update={
                    "private_input_sha256": hashlib.sha256(
                        c.private.model_dump_json().encode()
                    ).hexdigest()
                }
            )
        }
    )
    c.resource.spec = c.resource.spec.model_copy(
        update={"configuration": c.configuration}
    )
    proof = c.put(PROOF.read_bytes(), "map-native-layer-proof/1")
    return proof
