"""Concrete Group/native COPY facts on the shared readonly evaluation context."""

from collections.abc import Callable
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .evidence_schema import GroupEvidence, GroupFacts
from .tasks.group_spec import GroupSpec
from .tasks.group_capture import GroupCapturedFacts, same_group_state
from .tasks.group_environment import GroupEnvironmentChecks
from .evaluation_context import read_context, check_context, final_page
from .group_evaluation_capture import group_native_capture


class GroupEvaluationReads:
    def __init__(
        self,
        native_loader: Callable[[bytes, GroupSpec], GroupCapturedFacts],
        input_loader: Callable[[bytes, EvidenceRef, PublicTask], GroupSpec],
    ) -> None:
        self.native_loader, self.input_loader = native_loader, input_loader

    def __call__(
        self,
        contract: EvaluationContract,
        selected: GroupEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> GroupFacts:
        if (
            selected.environment_ref is None
            or selected.browser_spec_ref is None
            or selected.before is None
            or selected.after is None
            or selected.page is None
            or selected.trace_ref is None
        ):
            raise EvidenceNotFound(
                "Required original Group capture/context/trace missing"
            )
        reads = GroupEnvironmentChecks(reader, self.native_loader)
        context = read_context(
            reads,
            contract,
            selected.environment_ref,
            selected.browser_spec_ref,
            selected.trace_ref,
            control,
        )
        spec = reads.read(
            contract.completion_spec_ref, "gitlab-group-creation/1", GroupSpec, control
        )
        if spec.task != contract.identity:
            raise EvidenceIntegrityError(
                "Group evaluation changed original private identity"
            )
        native = reader.read(spec.native_contract_ref, control=control)
        if self.input_loader(native, spec.native_contract_ref, context.public) != spec:
            raise EvidenceIntegrityError(
                "Group evaluation changed original frozen contract"
            )
        env, trace = context.environment, context.trace
        _, site, snapshot = reads._environment(env, control)
        origin = snapshot.native_before.context.instance.endpoint
        check_context(
            reads, contract, context, site, origin, "gitlab_group_creation", control
        )
        before_intent, before = group_native_capture(
            reads,
            selected.before,
            contract,
            spec,
            site,
            snapshot,
            trace,
            env.snapshot_ref.sha256,
            control,
        )
        after_intent, after = group_native_capture(
            reads,
            selected.after,
            contract,
            spec,
            site,
            snapshot,
            trace,
            env.snapshot_ref.sha256,
            control,
        )
        original = reads.native(snapshot.native_before, snapshot.request, control)
        if not same_group_state(original, before):
            raise EvidenceIntegrityError(
                "Group evaluation shifted original native baseline"
            )
        first, last = before_intent.request.inspection, after_intent.request.inspection
        if (
            first.snapshot_ref != env.snapshot_ref
            or last.snapshot_ref != env.snapshot_ref
            or first.operation.operation_id == last.operation.operation_id
            or first.operation.recovery_ref != last.operation.recovery_ref
        ):
            raise EvidenceIntegrityError(
                "Group evaluation lost original distinct before/after captures"
            )
        initialization = context.browser.configuration.initialization
        if (
            not isinstance(initialization, GitlabGroupInitialization)
            or initialization.native_account_id != before.state.user.id
        ):
            raise EvidenceIntegrityError(
                "Group evaluation changed original native login account"
            )
        page = final_page(reads, context, selected.page, control)
        return GroupFacts(context.public, spec, before, after, page, trace, origin)
