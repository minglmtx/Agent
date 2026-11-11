"""Complete selected facts from existing private/public evidence ports, no site effects."""

import hashlib
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.domain.preparation import PreparedTask
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .evidence_schema import ImageEvidence, ImageFacts
from typing import Protocol
from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.domain.trace_journal import TraceSnapshot


class IssuedAxLoader(Protocol):
    def __call__(
        self,
        request: ActorRunRequest,
        snapshot: TraceSnapshot,
        trace: InteractionTrace,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> str: ...


from .tasks.image_environment import ImageEnvironmentChecks
from .tasks.image_spec import NativeImageSpec
from .tasks.image_binding import NativeImageInputLoader
from .evaluation_capture import native_capture, page_capture


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


class ImageEvaluationReads:
    def __init__(
        self, input_loader: NativeImageInputLoader, issued_loader: IssuedAxLoader
    ) -> None:
        self.input_loader, self.issued_loader = input_loader, issued_loader

    def __call__(
        self,
        contract: EvaluationContract,
        selected: ImageEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> ImageFacts:
        if (
            selected.environment_ref is None
            or selected.browser_spec_ref is None
            or selected.before is None
            or selected.after is None
            or selected.page is None
            or selected.trace_ref is None
            or selected.trace_snapshot_ref is None
        ):
            raise EvidenceNotFound(
                "Required original Reddit capture/context/trace missing"
            )
        reads = ImageEnvironmentChecks(reader)
        binding = reads.read(
            contract.task_contract_ref, "task-binding/1", TaskBinding, control
        )
        raw_public = public_bytes(
            reader, contract.public_task_ref, "public-task/1", control
        )
        public = PublicTask.model_validate_json(raw_public)
        if public.model_dump_json().encode() != raw_public:
            raise EvidenceIntegrityError("Noncanonical original Reddit public task")
        spec = reads.read(
            contract.completion_spec_ref,
            "reddit-native-image/1",
            NativeImageSpec,
            control,
        )
        if (
            binding.identity,
            public.identity,
            spec.task,
            binding.public_task_ref,
            binding.private_spec_ref,
        ) != (
            contract.identity,
            contract.identity,
            contract.identity,
            contract.public_task_ref,
            contract.completion_spec_ref,
        ):
            raise EvidenceIntegrityError(
                "Reddit evaluation changed original task binding"
            )
        native = reader.read(spec.native_contract_ref, control=control)
        if (
            self.input_loader(native, spec.native_contract_ref, public).private_spec
            != spec
        ):
            raise EvidenceIntegrityError(
                "Reddit evaluation changed original frozen contract"
            )
        if selected.trace_ref.size_bytes > 16 * 1024 * 1024:
            raise EvidenceIntegrityError("Original Reddit trace exceeds frozen budget")
        trace = reads.read(
            selected.trace_ref, "interaction-trace/1", InteractionTrace, control
        )
        env = reads.read(
            selected.environment_ref,
            "environment-selection/1",
            EnvironmentSelection,
            control,
        )
        _, site, snapshot = reads._environment(env, control)
        browser = reads.read(
            selected.browser_spec_ref,
            "browser-resource-spec/4",
            BrowserResourceSpec,
            control,
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
                "Reddit evaluation changed original resource/context"
            )
        initialization = browser.configuration.initialization
        if not isinstance(initialization, RedditNativeImageInitialization):
            raise EvidenceIntegrityError(
                "Reddit evaluation lost fixed original initialization"
            )
        prepared = reads.read(
            initialization.prepared_ref, "prepared-task/1", PreparedTask, control
        )
        if (
            prepared.scope != trace.scope
            or prepared.public_task != public
            or prepared.task_binding_ref != contract.task_contract_ref
            or initialization.site_ref != env.site_started_ref
            or initialization.endpoint
            != snapshot.native_before.context.instance.endpoint
        ):
            raise EvidenceIntegrityError(
                "Reddit evaluation changed original preparation"
            )
        for turn in trace.turns:
            if turn.interaction is not None:
                browser.check_operation(turn.interaction.operation, "execute")
        before_intent, before = native_capture(
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
        after_intent, after = native_capture(
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
        first, last = before_intent.request.inspection, after_intent.request.inspection
        if (
            first.snapshot_ref != env.snapshot_ref
            or last.snapshot_ref != env.snapshot_ref
            or first.operation.operation_id == last.operation.operation_id
            or first.operation.recovery_ref != last.operation.recovery_ref
        ):
            raise EvidenceIntegrityError(
                "Reddit evaluation lost original distinct before/after captures"
            )
        reference = reads.reference(snapshot.native_before, snapshot.request, control)
        snapshot.media_initialization.check_baseline(reference.capture.native_media)
        if before != reference.capture or (
            initialization.native_account_id,
            initialization.native_account_username,
        ) != (reference.account.id, reference.account.username):
            raise EvidenceIntegrityError(
                "Reddit evaluation changed original native login account"
            )
        stop = reads.read(trace.stop_evidence_ref, "trace-stop/1", ActorStop, control)
        request = reads.read(
            stop.request_ref, stop.request_ref.content_schema, ActorRunRequest, control
        )
        if request.schema_version != stop.request_ref.content_schema:
            raise EvidenceIntegrityError(
                "Reddit Actor request schema differs from original reference"
            )
        if (
            stop.scope,
            stop.reason,
            stop.generations,
            stop.interactions,
            stop.final_observation_ref,
        ) != (
            trace.scope,
            trace.stop_reason,
            trace.generations,
            trace.interactions,
            trace.final_observation_ref,
        ) or (
            request.scope,
            request.task,
            request.browser_allocation,
        ) != (
            trace.scope,
            public,
            browser.token,
        ):
            raise EvidenceIntegrityError(
                "Reddit judgment changed original sealed Actor request"
            )
        journal = reads.read(
            selected.trace_snapshot_ref,
            "trace-journal-snapshot/1",
            TraceSnapshot,
            control,
        )
        issued = self.issued_loader(request, journal, trace, reader, control)
        raw_observed = public_bytes(
            reader, trace.final_observation_ref, "observation/1", control
        )
        observed = Observation.model_validate_json(raw_observed)
        if observed.model_dump_json().encode() != raw_observed:
            raise EvidenceIntegrityError("Noncanonical original Reddit observation")
        page = page_capture(reads, selected.page, browser, trace, observed, control)
        return ImageFacts(public, spec, reference, before, after, page, trace, issued)
