"""Narrow live fresh-source engineering rights; never formal claim admission."""

import hashlib
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.run_plan import ExecutionWorkload
from lab_generate_skill.ports.lifecycle import OperationControl
from browser_resource_fixtures import ResourceCase as BrowserCase
from actor_source_protocol import ActorSource
from source_actor_plan import SourceActorPlan
from source_actor_projection import original_source_projection


class SourceActorAuthority:
    def __init__(
        self,
        source: ActorSource,
        browser: BrowserCase,
        session: EvidenceBrowserSession,
        plan: SourceActorPlan,
    ) -> None:
        self.source, self.browser, self.session, self.plan = (
            source,
            browser,
            session,
            plan,
        )

    def verify(
        self,
        request: ActorRunRequest,
        snapshot: TraceSnapshot,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        source, browser = self.source, self.browser
        if (
            request != self.plan.request
            or snapshot.plan != self.plan.trace
            or request.task != source.native.public
        ):
            raise OwnershipConflict("Original engineering source/run changed")
        if not isinstance(self.plan.run.workload, ExecutionWorkload):
            raise OwnershipConflict("Actor source requires original execution workload")
        projection = original_source_projection(
            request,
            snapshot.plan,
            source.c.evidence,
            control,
        )
        if projection != self.plan.projection:
            raise OwnershipConflict(
                "Actor view changed original frozen execution policy"
            )
        baseline = BaselineReceipt.model_validate_json(
            source.c.evidence.read(source.saved["baseline_ref"], control)
        )
        if (
            baseline != source.saved["baseline"]
            or baseline.status != "ready"
            or source.saved["baseline_inputs"].observation_ref
            != request.initial_observation_ref
        ):
            raise OwnershipConflict(
                "Original ready baseline/unique observation changed"
            )
        if (
            self.session.observation_ref
            != snapshot.project().current_observation(snapshot.plan)
            or self.session.engine.state != "ready"
        ):
            raise OwnershipConflict("Original browser is not at this exact live turn")
        for role, case in (("site", source.c), ("browser", browser)):
            key = hashlib.sha256(
                (
                    request.operation.operation_id
                    + ":"
                    + str(snapshot.revision)
                    + ":"
                    + role
                ).encode()
            ).hexdigest()
            op = case.op.model_copy(
                update={
                    "operation_id": "source-live-" + key,
                    "deadline": request.operation.deadline,
                    "mode": "cleanup",
                    "parent_operation_id": case.op.operation_id,
                    "cancellation_ref": None,
                }
            )
            if (
                case.spec.token.owner != request.scope.owner
                or case.journal.read(case.spec.token, op).state != "acquired"
            ):
                raise OwnershipConflict(
                    "Original exclusive source/browser resource no longer acquired"
                )
        control.checkpoint()
