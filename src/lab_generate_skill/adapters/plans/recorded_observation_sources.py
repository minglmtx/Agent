"""Closed source/window verification from original persistent evidence only.

This verifier cannot prepare an input, issue a cursor, read a website or acquire
the old instance. A recorded cursor remains historical data, never a new permit.
"""

from lab_generate_skill.domain.actor_prompt import ActorPublicTurn, ActorPrompt
from lab_generate_skill.domain.observation_read import ObservationReadRequest
from lab_generate_skill.domain.observation_read_progress import observation_request_key
from lab_generate_skill.policies.observation_proposals import (
    check_indexed_proposal,
    check_issued_continuation,
)
from lab_generate_skill.policies.actor_proposal_feedback import reject_proposal
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace import observation_progress_from_turns
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.policies.observation_index import (
    ObservationIndex,
    index_public_ax,
)
from lab_generate_skill.policies.observation_pages import observation_page
from lab_generate_skill.policies.observation_search import index_literal_search
from lab_generate_skill.ports.lifecycle import OperationControl


from lab_generate_skill.domain.observation_viewport import ObservationViewport
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.actor_rejection_progress import ActorRejectionProgress
from .observation_viewports import read_public_viewport


class RecordedActorObservationSources:
    def __init__(
        self,
        configuration: ActorContextConfiguration,
        evidence: EvidenceReader | None = None,
        *,
        rejections: ActorRejectionProgress | None = None,
    ) -> None:
        self.configuration = ActorContextConfiguration.model_validate(configuration)
        if not isinstance(
            self.configuration.policy.actor_projection, AdaptiveObservationProjection
        ):
            raise ValueError("Original explicit adaptive configuration required")
        self.evidence = evidence
        projection = self.configuration.policy.actor_projection
        assert isinstance(projection, AdaptiveObservationProjection)
        if projection.read_policy.schema_version == "observation-read-policy/2" and (
            rejections is None or evidence is None
        ):
            raise OwnershipConflict(
                "Closed policy2 source requires actual rejection evidence and verifier"
            )
        self.rejections = rejections
        self._viewport: ObservationViewport | None = None
        self._index: ObservationIndex | None = None
        self._reference: EvidenceRef | None = None
        self._verified_public: ActorPublicTurn | None = None
        self._cursor_bindings: dict[str, str] = {}

    def clear_inputs(self) -> None:
        self._index = None
        self._reference = None
        self._viewport = None
        self._verified_public = None
        self._cursor_bindings.clear()

    def prepare_public_source(
        self,
        request: ActorRunRequest,
        before: TraceSnapshot,
        operation: OperationContext,
        public: ActorPublicTurn,
        *,
        control: OperationControl,
        inputs: EvidenceReader | None = None,
    ) -> ActorPublicTurn:
        raise OwnershipConflict(
            "Closed source verification grants no input preparation or old-instance continuation"
        )

    def index_for_public(self, public: ActorPublicTurn) -> ObservationIndex | None:
        source = public.observation_source
        if source is None:
            raise OwnershipConflict("Explicit original recorded public source required")
        if self._reference != source.snapshot.observation_ref:
            self._cursor_bindings.clear()
            self._reference = source.snapshot.observation_ref
            self._index = None
            try:
                self._index = index_public_ax(
                    source.snapshot.observation_ref,
                    public.observation.record.model_dump_json().encode(),
                    public.observation,
                    source.snapshot.scope,
                    source.policy,
                    viewport=self._viewport,
                )
            except (ValueError, UnicodeError):
                pass
        return self._index

    def check_recorded_proposal(
        self,
        public: ActorPublicTurn,
        prompt: ActorPrompt,
        reading: ObservationReadRequest,
        *,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        source, view, index = (
            public.observation_source,
            prompt.observation_view,
            self._index,
        )
        if (
            public != self._verified_public
            or source is None
            or view is None
            or index is None
            or (view.snapshot, view.policy) != (source.snapshot, source.policy)
            or reading.snapshot != source.snapshot
            or source.eligibility != "local_supported"
        ):
            raise OwnershipConflict(
                "Recorded preflight has no just-verified original indexed input"
            )
        remaining = source.policy.reads_per_observation - source.reads_used
        if remaining <= 0:
            reject_proposal(
                "READ_QUOTA_EXHAUSTED",
                "No reads remain for this public snapshot.",
                "Use already displayed evidence or task-relevant browser controls; do not claim a site-wide search.",
                tool=reading.tool,
                actual=remaining,
                allowed=0,
            )
        if source.no_progress >= source.policy.consecutive_no_progress:
            raise OwnershipConflict(
                "Original recorded reading already reached its controlled stop"
            )
        check_indexed_proposal(index, reading)
        check_issued_continuation(reading, self._cursor_bindings)
        control.checkpoint()

    def verify_public_source(
        self,
        request: ActorRunRequest,
        before: TraceSnapshot,
        operation: OperationContext,
        public: ActorPublicTurn,
        recorded: ActorPublicTurn,
        *,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self._verified_public = None
        if any(
            getattr(public, name) != getattr(recorded, name)
            for name in ("task", "skill", "observation", "history", "memory")
        ):
            raise OwnershipConflict(
                "Recorded adaptive source changed original public task/history/observation"
            )
        source = recorded.observation_source
        projection = self.configuration.policy.actor_projection
        assert isinstance(projection, AdaptiveObservationProjection)
        if (
            source is None
            or source.snapshot.scope != request.scope
            or source.policy != projection.read_policy
            or source.snapshot.observation_ref
            != before.project().current_observation(before.plan)
        ):
            raise OwnershipConflict(
                "Recorded source changed original snapshot/policy/trace scope"
            )
        VerifiedEvidenceBody(
            source.snapshot.observation_ref,
            public.observation.record.model_dump_json().encode(),
        )
        if source.policy.schema_version == "observation-read-policy/2":
            assert self.rejections is not None
            if source.invalid_proposals != self.rejections.derive(
                before, source.snapshot.observation_ref, source.policy, control=control
            ):
                raise OwnershipConflict(
                    "Recorded source changed actual persisted invalid proposal progress"
                )
        self._viewport = read_public_viewport(
            recorded.observation, self.evidence, control
        )
        index = self.index_for_public(recorded)
        if index is not None and source.snapshot != index.snapshot:
            raise OwnershipConflict(
                "Recorded source changed the original indexed snapshot, including full-only sources"
            )
        supported = (
            index is not None
            and bool(index.nodes)
            and projection.supports_local(request.scope.task)
        )
        if supported != (source.eligibility == "local_supported"):
            raise OwnershipConflict(
                "Recorded source changed the qualified structure/task capability"
            )
        if not supported:
            self._verified_public = recorded
            return
        assert index is not None
        if source.snapshot != index.snapshot or source.tools != (
            "list_regions",
            "read_region",
            "search_regions",
        ):
            raise OwnershipConflict(
                "Recorded local source changed actual tool/snapshot declaration"
            )
        window = source.local_window
        if window is None:
            raise EvidenceIntegrityError("Original supported source window missing")
        progress = observation_progress_from_turns(
            tuple(before.project().turns), index.snapshot, source.policy
        )
        if (source.reads_used, source.no_progress) != (
            progress.reads_used,
            progress.no_progress,
        ):
            raise OwnershipConflict(
                "Recorded source changed actual original trace reading quota"
            )
        if progress.active is not None:
            if (
                source.window_origin != "actor_returned"
                or source.read_result_ref != progress.active.result_ref
            ):
                raise OwnershipConflict(
                    "Recorded window has no original returned reading"
                )
            VerifiedEvidenceBody(
                progress.active.result_ref, window.model_dump_json().encode()
            )
        else:
            if (
                source.window_origin != "automatic_initial"
                or source.read_result_ref is not None
                or window.request.tool != "list_regions"
            ):
                raise OwnershipConflict(
                    "Initial view cannot invent an Actor read/delivery"
                )
            if (
                window.request.request_id != "automatic-initial-directory"
                or window.request.continuation is not None
                or window.request.parent_region_id is not None
            ):
                raise OwnershipConflict(
                    "Automatic initial directory changed original bounded source scope"
                )
            expected = observation_page(
                index,
                window.request,
                offset=0,
                limit=source.policy.directory_entries,
                next_cursor=window.continuation or "no-continuation",
                search=index_literal_search(index),
            ).payload
            if expected != window:
                raise EvidenceIntegrityError(
                    "Recorded initial directory/required state differs from original public source"
                )
        if window.continuation is not None:
            binding = observation_request_key(
                window.request.model_copy(update={"continuation": None})
            )
            old = self._cursor_bindings.setdefault(window.continuation, binding)
            if (
                old != binding
                or len(self._cursor_bindings) > source.policy.reads_per_observation + 1
            ):
                raise EvidenceIntegrityError(
                    "Original recorded cursor provenance changed or exceeded its bound"
                )
        self._verified_public = recorded
        control.checkpoint()
