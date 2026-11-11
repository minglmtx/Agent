"""Current original Actor snapshot/window, with actual readonly result provenance.

One immutable source index and one active returned window; existing trace/store/
counter own persistence. No acquisition, website operation, model inference,
cross-attempt takeover or persistent checkpoint is introduced.
"""

import hashlib
import os
import threading
import unicodedata
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.domain.actor_observation_source import ActorObservationSource
from lab_generate_skill.domain.actor_observation_view import ActorObservationView
from lab_generate_skill.ports.actor_rejection_progress import ActorRejectionProgress
from lab_generate_skill.domain.context_budget import CountedContextInput
from lab_generate_skill.domain.observation_read import (
    PublicObservationSnapshot,
    ListObservationRegions,
    ObservationReadRequest,
    ObservationReadPayload,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation_read_progress import ObservationReadProgress
from lab_generate_skill.domain.observation_read_return import (
    ReturnedObservationRead,
    ObservationReadUnconfirmed,
)
from lab_generate_skill.domain.observation_read_fact import ObservationReadFailure
from lab_generate_skill.domain.trace import observation_progress_from_turns
from lab_generate_skill.domain.trace_events import ReadObserved
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.actor import ActorRunAuthority
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.trace_journal import TraceJournal
from lab_generate_skill.ports.context_projection import (
    ContextTokenCounter,
    ContextCountEvidenceVerifier,
    ContextCountInputReview,
)
from lab_generate_skill.policies.observation_index import (
    ObservationIndex,
    index_public_ax,
)
from lab_generate_skill.policies.observation_display import observation_read_body
from lab_generate_skill.actor.adaptive_protection import validate_local_source
from lab_generate_skill.adapters.models.observation_body_counts import (
    ActorObservationBodyCounts,
)
from .observation_reads import SnapshotObservationReads
from .reading_bodies import PublishedReadingBodies


from .observation_viewports import read_public_viewport


class ActorObservationSources:
    def __init__(
        self,
        request: ActorRunRequest,
        journal: TraceJournal,
        evidence: EvidenceStore,
        authority: ActorRunAuthority,
        controls: OperationControls,
        configuration: ActorContextConfiguration,
        counters: ContextTokenCounter,
        count_reviews: ContextCountEvidenceVerifier,
        *,
        rejections: ActorRejectionProgress | None = None,
    ) -> None:
        self.request = ActorRunRequest.model_validate(request)
        self.configuration = ActorContextConfiguration.model_validate(configuration)
        projection = self.configuration.policy.actor_projection
        if (
            not isinstance(projection, AdaptiveObservationProjection)
            or projection.read_policy.unicode_version != unicodedata.unidata_version
        ):
            raise ValueError(
                "Actual adaptive projection and exact frozen Unicode implementation required"
            )
        self.projection = projection
        if (
            projection.read_policy.schema_version == "observation-read-policy/2"
            and rejections is None
        ):
            raise OwnershipConflict(
                "Policy2 requires actual persisted rejection progress"
            )
        self.rejections = rejections
        self.journal, self.evidence, self.authority, self.controls = (
            journal,
            evidence,
            authority,
            controls,
        )
        self.bodies = PublishedReadingBodies(evidence)
        self.counts = ActorObservationBodyCounts(
            counters,
            self.bodies,
            self.configuration.profiles[0],
            self.configuration.policy,
            projection.read_policy,
        )
        self.count_reviews = count_reviews
        self._pid, self._thread = os.getpid(), threading.get_ident()
        self._closed = False
        self._index: ObservationIndex | None = None
        self._reader: SnapshotObservationReads | None = None
        self._initial_window: ObservationReadPayload | None = None
        self._source_reference: EvidenceRef | None = None
        self._prepared: ActorPublicTurn | None = None
        self._last_request: tuple[ObservationReadRequest, OperationContext] | None = (
            None
        )
        self._returned: ReturnedObservationRead | None = None
        self._error: BaseException | None = None
        self._verified_count: CountedContextInput | None = None

    def _local(self) -> None:
        if self._closed or (os.getpid(), threading.get_ident()) != (
            self._pid,
            self._thread,
        ):
            raise OwnershipConflict(
                "Original Actor observation source lifetime changed"
            )

    def clear_inputs(self) -> None:
        if (os.getpid(), threading.get_ident()) != (self._pid, self._thread):
            raise OwnershipConflict(
                "Original source cannot close in a foreign process/thread"
            )
        if self._reader is not None:
            self._reader.close()
        self._closed = True
        self._index = self._reader = self._initial_window = self._prepared = None
        self._last_request = self._returned = self._error = self._verified_count = None
        self.bodies.clear()

    def require_current(
        self,
        snapshot: PublicObservationSnapshot,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> None:
        self._local()
        if (
            snapshot.scope != self.request.scope
            or self._index is None
            or snapshot != self._index.snapshot
        ):
            raise OwnershipConflict(
                "Reading changed current original public scope/index"
            )
        if (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.mode,
        ) != (
            snapshot.scope.owner.run_id,
            snapshot.scope.owner.owner_id,
            snapshot.scope.attempt_id,
            "execute",
        ):
            raise OwnershipConflict("Reading operation changed original attempt")
        actual = self.journal.read(operation)
        view = actual.project()
        if (
            view.sealed is not None
            or view.current_observation(actual.plan) != snapshot.observation_ref
        ):
            raise OwnershipConflict(
                "Reading snapshot is no longer the current original trace observation"
            )
        self.authority.verify(self.request, actual, control)
        control.checkpoint()

    def index_for_public(self, public: ActorPublicTurn) -> ObservationIndex | None:
        self._local()
        source = public.observation_source
        if source is None:
            raise OwnershipConflict("Explicit original public source required")
        if self._index is None:
            if source.snapshot.structure != "opaque_public_text/1":
                raise OwnershipConflict("Original qualified source index is missing")
            return None
        if (
            self._index.snapshot != source.snapshot
            or self._index.text != public.observation.text
        ):
            raise OwnershipConflict(
                "Source index does not belong to this actual public input"
            )
        return self._index

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
        self._local()
        if (
            request != self.request
            or before.plan.scope != request.scope
            or public.schema_version != "actor-public-turn/1"
        ):
            raise OwnershipConflict(
                "Adaptive producer changed original request/public source"
            )
        reference = before.project().current_observation(before.plan)
        policy = self.projection.read_policy
        if self._source_reference != reference:
            if self._reader is not None:
                self._reader.close()
            self._reader = None
            self._index = None
            self._initial_window = None
            self._source_reference = reference
            self._returned = self._last_request = self._error = self._verified_count = (
                None
            )
            try:
                self._index = index_public_ax(
                    reference,
                    public.observation.record.model_dump_json().encode(),
                    public.observation,
                    request.scope,
                    policy,
                    viewport=read_public_viewport(
                        public.observation, self.evidence, control
                    ),
                )
            except (ValueError, UnicodeError):
                # Unsupported public structure can keep its original complete
                # input if the hard gate permits. Integrity/ownership never fall back.
                self._index = None
            if (
                self._index is not None
                and self._index.nodes
                and self.projection.supports_local(request.scope.task)
            ):
                self._reader = SnapshotObservationReads(
                    self._index, self.bodies, self, self.counts
                )
                initial = ListObservationRegions(
                    request_id="automatic-initial-directory",
                    snapshot=self._index.snapshot,
                    output_tokens=policy.body_max_tokens,
                )
                self._initial_window = self._reader.automatic_directory(
                    initial, operation, control=control
                ).payload
        observed = public.observation.record
        assert (
            observed.active_tab_id is not None and public.observation.text is not None
        )
        snapshot = (
            self._index.snapshot
            if self._index is not None
            else PublicObservationSnapshot(
                observation_ref=reference,
                scope=request.scope,
                sequence=observed.sequence,
                tab_id=observed.active_tab_id,
                frame_id=None,
                text_sha256=hashlib.sha256(
                    public.observation.text.encode()
                ).hexdigest(),
                policy_sha256=policy.digest,
                structure="opaque_public_text/1",
            )
        )
        fields = dict(
            snapshot=snapshot,
            policy=policy,
            eligibility="full_required",
            reason="unsupported_structure_or_task_contract",
            tools=(),
            local_window=None,
            window_origin="none",
            read_result_ref=None,
            reads_used=0,
            no_progress=0,
        )
        if policy.schema_version == "observation-read-policy/2":
            assert self.rejections is not None
            fields.update(
                schema_version="actor-observation-source/2",
                invalid_proposals=self.rejections.derive(
                    before, reference, policy, control=control, inputs=inputs
                ),
            )
        if self._reader is not None:
            progress = observation_progress_from_turns(
                tuple(before.project().turns), snapshot, policy
            )
            active = progress.active
            if active is None:
                window = self._initial_window
                origin = "automatic_initial"
            else:
                actual = self._reader.active_return
                if actual is None or actual.record != active:
                    raise OwnershipConflict(
                        "Original returned reading cannot be reconstructed as a live continuation"
                    )
                window = actual.payload
                origin = "actor_returned"
            fields.update(
                eligibility="local_supported",
                reason="registered_original_tab_ax_reader",
                tools=("list_regions", "read_region", "search_regions"),
                local_window=window,
                window_origin=origin,
                read_result_ref=None if active is None else active.result_ref,
                reads_used=progress.reads_used,
                no_progress=progress.no_progress,
            )
        source = ActorObservationSource.model_validate(fields)
        recorded = ActorPublicTurn(
            schema_version="actor-public-turn/2",
            task=public.task,
            skill=public.skill,
            observation=public.observation,
            history=public.history,
            memory=public.memory,
            observation_source=source,
        )
        self._prepared = recorded
        return recorded

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
        self._local()
        control.checkpoint()
        if (
            request != self.request
            or self._prepared != recorded
            or any(
                getattr(public, name) != getattr(recorded, name)
                for name in ("task", "skill", "observation", "history", "memory")
            )
        ):
            raise OwnershipConflict(
                "Recorded source differs from this original prepared public graph"
            )
        source = recorded.observation_source
        if (
            source is None
            or source.snapshot.scope != request.scope
            or source.snapshot.observation_ref
            != before.project().current_observation(before.plan)
        ):
            raise OwnershipConflict("Recorded source changed original trace/snapshot")
        if source.read_result_ref is not None:
            progress = observation_progress_from_turns(
                tuple(before.project().turns), source.snapshot, source.policy
            )
            if (
                progress.active is None
                or progress.active.result_ref != source.read_result_ref
                or source.local_window is None
            ):
                raise OwnershipConflict(
                    "Source has no actual original returned read event"
                )
            VerifiedEvidenceBody(
                source.read_result_ref, source.local_window.model_dump_json().encode()
            )
        if source.eligibility == "local_supported":
            index = self.index_for_public(recorded)
            assert index is not None
            validate_local_source(recorded, index)

    def check_proposal(
        self,
        request: ObservationReadRequest,
        view: ActorObservationView,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> None:
        self._local()
        control.checkpoint()
        source = None if self._prepared is None else self._prepared.observation_source
        if (
            source is None
            or self._reader is None
            or view.snapshot != source.snapshot
            or view.policy != source.policy
            or view.tools != source.tools
            or request.snapshot != source.snapshot
        ):
            raise OwnershipConflict(
                "Proposal preflight requires this prepared snapshot and actual retained reader"
            )
        if (operation.run_id, operation.owner_id, operation.attempt_id) != (
            self.request.scope.owner.run_id,
            self.request.scope.owner.owner_id,
            self.request.scope.attempt_id,
        ):
            raise OwnershipConflict(
                "Proposal preflight changed original operation owner"
            )
        actual = self.journal.read(operation)
        projected = actual.project()
        if (
            projected.sealed is not None
            or projected.current_observation(actual.plan)
            != source.snapshot.observation_ref
        ):
            raise OwnershipConflict(
                "Proposal preflight no longer has the original current observation"
            )
        self.authority.verify(self.request, actual, control)
        progress = observation_progress_from_turns(
            tuple(projected.turns), source.snapshot, source.policy
        )
        if (view.reads_used, view.no_progress) != (
            progress.reads_used,
            progress.no_progress,
        ):
            raise OwnershipConflict("Proposal view changed actual read progress")
        self._reader.check_proposal(request, progress=progress, control=control)

    def read(
        self,
        request: ObservationReadRequest,
        operation: OperationContext,
        *,
        progress: ObservationReadProgress,
        control: OperationControl,
        retention_control: OperationControl | None = None,
    ) -> ReturnedObservationRead:
        self._local()
        if self._reader is None:
            raise OwnershipConflict("No actual current registered readonly capability")
        self._last_request = (request, operation)
        self._returned = None
        self._error = None
        self.bodies.begin()
        try:
            self._returned = self._reader.read(
                request,
                operation,
                progress=progress,
                control=control,
                retention_control=retention_control,
            )
            return self._returned
        except BaseException as error:
            self._error = error
            if (
                isinstance(error, ObservationReadUnconfirmed)
                and error.result_ref is not None
            ):
                try:
                    self._returned = ReturnedObservationRead(
                        result_ref=error.result_ref,
                        payload=error.payload,
                        body=error.body,
                        count=error.count,
                    )
                except (ValueError, EvidenceIntegrityError, OwnershipConflict):
                    pass  # Preserve the original error and unvalidated candidate reference.
            raise

    def reading_inputs(
        self, event: ReadObserved, control: OperationControl
    ) -> EvidenceReader:
        self._local()
        control.checkpoint()
        return self.bodies

    def verify_reading(
        self,
        before: TraceSnapshot,
        event: ReadObserved,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._local()
        pending = before.project().reading
        fact = event.reading
        if (
            pending is None
            or self._last_request != (fact.request, fact.operation)
            or pending.decision.read_request != fact.request
        ):
            raise OwnershipConflict(
                "Read result has no exact original registered readonly call"
            )
        if fact.result is not None:
            actual = self._returned
            if actual is None or actual.record != fact.result or self._index is None:
                raise OwnershipConflict(
                    "Read result differs from this original returned body/count"
                )
            if actual.body != observation_read_body(actual.payload):
                raise EvidenceIntegrityError(
                    "Read result changed actual displayed original body"
                )
            if self._verified_count != actual.count:
                reviewer = (
                    self.count_reviews.with_inputs(self.bodies)
                    if isinstance(self.count_reviews, ContextCountInputReview)
                    else self.count_reviews
                )
                measured = reviewer.verify(
                    actual.count,
                    self.configuration.profiles[0],
                    self.configuration.policy,
                    control=control,
                )
                if measured != actual.count.measurement:
                    raise EvidenceIntegrityError(
                        "Original native read body frames differ from returned measurement"
                    )
                self._verified_count = actual.count
        if fact.outcome != "returned" and self._error is None:
            raise OwnershipConflict("Read failure has no original registered error")
        if fact.failure_ref is not None:
            assert self._error is not None
            raw = self.bodies.read(fact.failure_ref, control)
            VerifiedEvidenceBody(fact.failure_ref, raw)
            diagnostic = ObservationReadFailure.model_validate_json(raw)
            expected_ref = (
                self._error.result_ref
                if isinstance(self._error, ObservationReadUnconfirmed)
                else None
            )
            expected = ObservationReadFailure(
                generation_id=fact.generation_id,
                request=fact.request,
                error_type=type(self._error).__name__,
                message=str(self._error)[:4096],
                returned_result_ref=expected_ref,
            )
            if diagnostic != expected:
                raise EvidenceIntegrityError(
                    "Read failure evidence differs from the original registered error"
                )
        control.checkpoint()
