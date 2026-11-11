"""Shared readonly original public/trace/browser joins, with no family dispatch."""

from dataclasses import dataclass
import hashlib
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.preparation import PreparedTask
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .private_state_reads import GitlabPrivateReads
from .evidence_schema import GitlabPageCapture, GitlabPageHealth
from .evaluation_capture import page_capture


def public_bytes(
    reader: EvidenceReader, ref: EvidenceRef, schema: str, control: OperationControl
) -> bytes:
    if (ref.visibility, ref.media_type, ref.content_schema) != (
        "public",
        "application/json",
        schema,
    ) or not 0 < ref.size_bytes <= 2 * 1024 * 1024:
        raise EvidenceIntegrityError(
            "Bounded original public evaluation evidence required"
        )
    raw = reader.read(ref, control=control)
    if type(raw) is not bytes or (len(raw), hashlib.sha256(raw).hexdigest()) != (
        ref.size_bytes,
        ref.sha256,
    ):
        raise EvidenceIntegrityError("Original public evaluation bytes changed")
    return raw


@dataclass(frozen=True)
class GitlabEvaluationContext:
    binding: TaskBinding
    public: PublicTask
    trace: InteractionTrace
    environment: EnvironmentSelection
    browser: BrowserResourceSpec


def read_context(
    reads: GitlabPrivateReads,
    contract: EvaluationContract,
    environment_ref: EvidenceRef,
    browser_ref: EvidenceRef,
    trace_ref: EvidenceRef,
    control: OperationControl,
) -> GitlabEvaluationContext:
    binding = reads.read(
        contract.task_contract_ref, "task-binding/1", TaskBinding, control
    )
    raw = public_bytes(reads.store, contract.public_task_ref, "public-task/1", control)
    public = PublicTask.model_validate_json(raw)
    if public.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError("Noncanonical original GitLab public task")
    if (
        binding.identity,
        public.identity,
        binding.public_task_ref,
        binding.private_spec_ref,
    ) != (
        contract.identity,
        contract.identity,
        contract.public_task_ref,
        contract.completion_spec_ref,
    ):
        raise EvidenceIntegrityError("GitLab evaluation changed original task binding")
    if trace_ref.size_bytes > 16 * 1024 * 1024:
        raise EvidenceIntegrityError("Original GitLab trace exceeds frozen budget")
    trace = reads.read(trace_ref, "interaction-trace/1", InteractionTrace, control)
    env = reads.read(
        environment_ref, "environment-selection/1", EnvironmentSelection, control
    )
    browser = reads.read(
        browser_ref, "browser-resource-spec/4", BrowserResourceSpec, control
    )
    return GitlabEvaluationContext(binding, public, trace, env, browser)


def check_context(
    reads: GitlabPrivateReads,
    contract: EvaluationContract,
    context: GitlabEvaluationContext,
    site: SiteResourceSpec,
    endpoint: str,
    initialization_kind: str,
    control: OperationControl,
) -> None:
    binding, public, trace, env, browser = (
        context.binding,
        context.public,
        context.trace,
        context.environment,
        context.browser,
    )
    if (
        trace.scope.task != contract.identity
        or trace.scope.attempt_id != contract.attempt_id
        or env.scope != trace.scope
        or env.spec_ref != binding.baseline_ref
        or site.token.owner != trace.scope.owner
        or browser.configuration.spec.scope != trace.scope
        or browser.configuration.spec.task != public
        or browser.slurm.execution != site.slurm.execution
        or browser.slurm.parent != site.slurm.parent
        or browser.token.owner != trace.scope.owner
        or browser.configuration.installation != site.configuration.installation
    ):
        raise EvidenceIntegrityError(
            "GitLab evaluation changed original resource/context"
        )
    initialization = browser.configuration.initialization
    if initialization is None or initialization.kind != initialization_kind:
        raise EvidenceIntegrityError(
            "GitLab evaluation lost fixed original initialization"
        )
    # Kind validation is explicit at each concrete family caller. The shared
    # union includes other sites and must never guess their preparation fields.
    from lab_generate_skill.domain.gitlab_browser_initialization import (
        GitlabSshKeyInitialization,
        GitlabGroupInitialization,
    )

    if not isinstance(
        initialization, (GitlabSshKeyInitialization, GitlabGroupInitialization)
    ):
        raise EvidenceIntegrityError("Original typed GitLab initialization required")
    prepared = reads.read(
        initialization.prepared_ref, "prepared-task/1", PreparedTask, control
    )
    if (
        prepared.scope != trace.scope
        or prepared.public_task != public
        or prepared.task_binding_ref != contract.task_contract_ref
        or initialization.site_ref != env.site_started_ref
        or initialization.endpoint != endpoint
    ):
        raise EvidenceIntegrityError("GitLab evaluation changed original preparation")
    for turn in trace.turns:
        if turn.interaction is not None:
            browser.check_operation(turn.interaction.operation, "execute")


def final_page(
    reads: GitlabPrivateReads,
    context: GitlabEvaluationContext,
    pair: GitlabPageCapture,
    control: OperationControl,
) -> GitlabPageHealth:
    trace = context.trace
    stop = trace.stop_evidence_ref
    if (stop.visibility, stop.content_schema) != ("private", "trace-stop/1") or not (
        0 < stop.size_bytes <= 2 * 1024 * 1024
    ):
        raise EvidenceIntegrityError("Original bounded trace stop evidence required")
    raw = reads.store.read(stop, control=control)
    if type(raw) is not bytes or (len(raw), hashlib.sha256(raw).hexdigest()) != (
        stop.size_bytes,
        stop.sha256,
    ):
        raise EvidenceIntegrityError("Original trace stop bytes changed")
    raw_observed = public_bytes(
        reads.store, trace.final_observation_ref, "observation/1", control
    )
    observed = Observation.model_validate_json(raw_observed)
    if observed.model_dump_json().encode() != raw_observed:
        raise EvidenceIntegrityError("Noncanonical original GitLab observation")
    return page_capture(reads, pair, context.browser, trace, observed, control)
