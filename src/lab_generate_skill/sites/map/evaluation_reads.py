"""Read-only selected Map judgment graph over the existing capture/file ports."""

from collections.abc import Callable
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_state_artifacts import MapStateFileReader
from lab_generate_skill.ports.evaluation_evidence import (
    EvaluationEvidenceReader,
    TraceAnswerReader,
)
from .evidence_schema import MapOverlayEvidence, MapCapturePair
from .evaluation_trace import sealed_map_trace
from .evaluation_guard import complete_final_guard
from .terminal_evidence import TerminalMapEvidence
from .terminal_files import private_bytes
from .reference_evidence import MapReferenceRead
from .page_evidence import terminal_page_health
from .overlay_evidence import original_overlay_checks
from .tasks.overlay_environment import OverlayEnvironmentChecks
from .tasks.overlay_spec import NativeOverlaySpec
from .tasks.overlay_input import bind_overlay_inputs
from .state_rules import object_json

TerminalLoader = Callable[
    [EvidenceReader, EvidenceRef, OperationControl], TerminalMapEvidence
]
ReferenceLoader = Callable[
    [EvidenceReader, MapCapturePair, TerminalMapEvidence, OperationControl],
    MapReferenceRead,
]
ServedLoader = Callable[[TerminalMapEvidence, OperationControl], bool]


class MapEvaluationReads:
    def __init__(
        self,
        site: SiteResourceSpec,
        started: SiteResourceStarted,
        files: MapStateFileReader,
        terminal: TerminalLoader,
        reference: ReferenceLoader,
        served: ServedLoader,
        model_reads: Callable[
            [EvidenceReader, OperationControl], EvaluationEvidenceReader
        ],
        answer_reader: TraceAnswerReader,
    ) -> None:
        self.site, self.started, self.files = site, started, files
        self.terminal, self.reference, self.served = terminal, reference, served
        self.model_reads, self.answer_reader = model_reads, answer_reader

    def __call__(
        self,
        contract: EvaluationContract,
        selected: MapOverlayEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> dict[str, bool]:
        if (
            selected.environment_ref is None
            or selected.terminal_ref is None
            or selected.page is None
            or selected.references is None
            or selected.final_guard is None
            or selected.browser_closure_ref is None
            or selected.trace_ref is None
            or selected.trace_snapshot_ref is None
        ):
            raise EvidenceNotFound(
                "Original Map environment/terminal/trace/final guard missing"
            )
        reads = self.model_reads(reader, control)
        binding = reads.read(contract.task_contract_ref, "task-binding/1", TaskBinding)
        public = reads.read(
            contract.public_task_ref, "public-task/1", PublicTask, public=True
        )
        private = reads.read(
            contract.completion_spec_ref, "map-native-overlay/1", NativeOverlaySpec
        )
        native = private_bytes(
            reader, private.native_contract_ref, "map-native-contract/1", control
        )
        if (
            (binding.identity, public.identity, private.task)
            != (contract.identity,) * 3
            or binding.public_task_ref != contract.public_task_ref
            or binding.private_spec_ref != contract.completion_spec_ref
            or bind_overlay_inputs(
                object_json(native), private.native_contract_ref, public
            ).private_spec
            != private
        ):
            raise EvidenceIntegrityError(
                "Map evaluation changed original task/contract meaning"
            )
        selected_env = reads.read(
            selected.environment_ref, "environment-selection/1", EnvironmentSelection
        )
        states = OverlayEnvironmentChecks(reader, self.files, self.site, self.started)
        env = states._environment(selected_env, control)
        terminal = self.terminal(reader, selected.terminal_ref, control)
        initial, browser = terminal.initial, terminal.initial.browser
        init = browser.configuration.initialization
        prepare = reads.read(
            initial.selection.preparation.selection.request_ref,
            "site-task-request/2",
            SiteTaskRequest,
        )
        if (
            selected_env.scope != initial.prepared.scope
            or initial.prepared.scope.attempt_id != contract.attempt_id
            or initial.prepared.task_binding_ref != contract.task_contract_ref
            or initial.prepared.private_checks_ref != contract.completion_spec_ref
            or initial.prepared.public_task != public
            or selected_env.spec_ref != binding.baseline_ref
            or not isinstance(init, MapNativeInitialization)
            or init.site_ref != selected_env.site_started_ref
            or prepare.snapshot_ref != selected_env.snapshot_ref
            or browser.slurm.execution != env.site.slurm.execution
            or browser.slurm.parent != env.site.slurm.parent
            or browser.configuration.installation != env.site.configuration.installation
        ):
            raise EvidenceIntegrityError(
                "Map evaluation changed original preparation/environment/browser"
            )
        page = terminal_page_health(
            terminal,
            reader,
            selected.page.intent_ref,
            selected.page.result_ref,
            control,
        )
        sealed_map_trace(selected, terminal, page, reads, self.answer_reader)
        closure = reads.read(
            selected.browser_closure_ref, "closure-receipt/1", ClosureReceipt
        )
        complete_final_guard(
            selected.final_guard,
            closure,
            terminal,
            env,
            states,
            selected_env.snapshot_ref,
            control,
        )
        references = tuple(
            self.reference(reader, pair, terminal, control)
            for pair in selected.references
        )
        checks = original_overlay_checks(
            terminal,
            references,
            page,
            served=self.served(terminal, control),
            control=control,
        )
        checks["original_complete_persistent_state_unchanged"] = True
        return checks
