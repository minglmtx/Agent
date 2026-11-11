"""Read original navigation declarations, environment, trace and full native guard."""

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
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.map_navigation_scope import check_page_navigation_scope
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_state_artifacts import MapStateFileReader
from lab_generate_skill.ports.evaluation_evidence import EvaluationEvidenceReader
from .evidence_schema import MapNavigationEvidence, NavigationOutcome
from .navigation_terminal_evidence import NavigationTerminalEvidence
from .evaluation_guard import complete_final_guard
from .terminal_files import private_bytes
from .tasks.overlay_environment import OverlayEnvironmentChecks
from .tasks.navigation_spec import NavigationSpec
from .tasks.navigation_input import bind_navigation_inputs
from .state_rules import object_json
from .navigation_rules import navigation_outcome

TerminalLoader = Callable[
    [EvidenceReader, EvidenceRef, OperationControl], NavigationTerminalEvidence
]


class NavigationEvaluationReads:
    def __init__(
        self,
        site: SiteResourceSpec,
        started: SiteResourceStarted,
        files: MapStateFileReader,
        terminal: TerminalLoader,
        model_reads: Callable[
            [EvidenceReader, OperationControl], EvaluationEvidenceReader
        ],
    ) -> None:
        self.site, self.started, self.files = site, started, files
        self.terminal, self.model_reads = terminal, model_reads

    def __call__(
        self,
        contract: EvaluationContract,
        selected: MapNavigationEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> NavigationOutcome:
        if (
            selected.environment_ref is None
            or selected.terminal_ref is None
            or selected.final_guard is None
            or selected.browser_closure_ref is None
        ):
            raise EvidenceNotFound(
                "Original navigation environment/terminal/closure/full guard missing"
            )
        reads = self.model_reads(reader, control)
        binding = reads.read(contract.task_contract_ref, "task-binding/1", TaskBinding)
        public = reads.read(
            contract.public_task_ref, "public-task/1", PublicTask, public=True
        )
        private = reads.read(
            contract.completion_spec_ref, "map-navigation-spec/1", NavigationSpec
        )
        native = private_bytes(
            reader, private.native_contract_ref, "map-native-contract/1", control
        )
        check_page_navigation_scope(
            contract.identity, private.native_contract_ref.sha256
        )
        if (
            (binding.identity, public.identity, private.task)
            != (contract.identity,) * 3
            or binding.public_task_ref != contract.public_task_ref
            or binding.private_spec_ref != contract.completion_spec_ref
            or bind_navigation_inputs(
                object_json(native),
                private.native_contract_ref,
                public,
                private.binding,
            ).private_spec
            != private
            or private.completion.map_route is not None
        ):
            raise EvidenceIntegrityError(
                "Navigation judgment changed original selected task/contract meaning"
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
            or not isinstance(init, MapNavigationInitialization)
            or init.site_ref != selected_env.site_started_ref
            or prepare.snapshot_ref != selected_env.snapshot_ref
            or browser.slurm.execution != env.site.slurm.execution
            or browser.slurm.parent != env.site.slurm.parent
            or browser.configuration.installation != env.site.configuration.installation
        ):
            raise EvidenceIntegrityError(
                "Navigation judgment changed original preparation/environment/browser"
            )
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
        control.checkpoint()
        return navigation_outcome(
            private,
            terminal.page.original_page(),
            site_origin=init.endpoint.rstrip("/"),
            runtime_error=False,
            selected_records_unchanged=True,
        )
