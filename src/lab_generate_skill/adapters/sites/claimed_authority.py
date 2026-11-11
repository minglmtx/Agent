"""Original claimed Map site permission, composed with the existing physical observer.

Use as ObservedSiteResourceAuthority.source, then TaskSiteAuthority.source. Native
requests are admitted exclusively by the existing once-bound native supplier.
Residual files stay in their declared private root until the outer owner disposes
them after confirmed domain close and full recovery; no implicit shared reuse.
"""

import json
import os
from pathlib import Path
from typing import Literal
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceReady,
    SiteResourceAttempt,
    SiteStepClosed,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.ports.lifecycle import OperationControl


class ClaimedSiteResourceAuthority:
    def __init__(
        self,
        owner: ClaimedRunResourceOwner,
        spec: SiteResourceSpec,
        acquisition: OperationContext,
    ) -> None:
        if not isinstance(owner, ClaimedRunResourceOwner):
            raise TypeError("Original claimed execution owner required")
        self.owner, self.spec, self.acquisition = (
            owner,
            SiteResourceSpec.model_validate(spec),
            OperationContext.model_validate(acquisition),
        )
        self.spec.check_operation(self.acquisition, "execute")
        self.ready: SiteResourceReady | None = None
        self.started: SiteInstanceStarted | None = None
        self._spawn = self._closing = False
        self.verify_site_inputs()

    def verify_site_inputs(self) -> None:
        owner = self.owner
        inputs = self.spec.configuration.map_inputs
        if not isinstance(inputs, MapNavigationWorkerInputs) or (
            self.spec.token.owner != owner.run.owner
            or inputs.scope.owner != owner.run.owner
            or inputs.scope.task != owner.task.identity
            or self.spec.slurm.execution != owner.authority.execution
            or self.spec.slurm.parent != owner.authority.controller
        ):
            raise OwnershipConflict(
                "Original current Map task/site/controller required"
            )

    def _require(
        self,
        configuration: SiteWorkerConfiguration,
        op: OperationContext,
        control: OperationControl,
        *,
        cleanup: bool,
    ) -> None:
        if configuration != self.spec.configuration:
            raise OwnershipConflict("Claimed site changed original configuration")
        self.spec.check_operation(op, "cleanup" if cleanup else "execute")
        if not cleanup and (op != self.acquisition or self._closing):
            raise OwnershipConflict("Original site acquisition is no longer admissible")
        if cleanup and op.parent_operation_id != self.acquisition.operation_id:
            raise OwnershipConflict("Site cleanup changed original acquisition parent")
        self.owner.require(op, control, new_work=not cleanup)

    def authorize_spawn(
        self, spec: SiteResourceSpec, op: OperationContext, control: OperationControl
    ) -> None:
        if spec != self.spec or self._spawn:
            raise OwnershipConflict("Original site spawn permission is one-shot")
        self.spec.check_operation(op, "execute")
        if op != self.acquisition:
            raise OwnershipConflict("Site changed original acquisition operation")
        self.owner.caller(op, control)
        self._spawn = True
        self._require(spec.configuration, op, control, cleanup=False)
        self.verify_source(op, control)
        root = Path(spec.configuration.files.node_root)
        parent = root.parent
        if (
            root.exists()
            or root.is_symlink()
            or not parent.is_relative_to("/tmp")
            or parent == Path("/tmp")
            or parent.resolve(strict=True) != parent
            or parent.stat().st_uid != os.getuid()
        ):
            raise OwnershipConflict(
                "Site requires its fresh original private node root"
            )

    def verify_source(self, op: OperationContext, control: OperationControl) -> None:
        spec = self.spec
        inputs = spec.configuration.map_inputs
        if not isinstance(inputs, MapNavigationWorkerInputs):
            raise OwnershipConflict("Original Map navigation input required")
        declared = self.owner.task_source(op, control)
        if (
            inputs.scope.attempt_id != declared.intent.binding.attempt_id
            or inputs.origin.source_context_receipt_ref != declared.context_receipt_ref
        ):
            raise OwnershipConflict(
                "Site replaced original source attempt/origin qualification"
            )
        from lab_generate_skill.adapters.map_runtime.readonly_authority import (
            verify_original_readonly_source,
        )

        verify_original_readonly_source(self.owner, spec, op, control)

    def verify(
        self,
        config: SiteWorkerConfiguration,
        phase: Literal["configure", "start", "close"],
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        cleanup = phase == "close"
        self._require(config, op, control, cleanup=cleanup)
        if cleanup:
            self._closing = True
        elif not self._spawn or (
            phase == "start" and (self.ready is None or self.started is not None)
        ):
            raise OwnershipConflict(
                "Original fixed worker must be acquired before native start"
            )

    def verify_ready(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self._require(spec.configuration, op, control, cleanup=False)
        if (
            spec != self.spec
            or self.ready is not None
            or ready.worker.owner_guard.controller != spec.slurm.parent.writer
        ):
            raise OwnershipConflict(
                "Original independently observed site worker required once"
            )
        # The enclosing ObservedSiteResourceAuthority independently checks the
        # actual held process/cgroup and this exact role-bound raw observation.
        self.ready = SiteResourceReady.model_validate(ready)

    def verify_started(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        started: SiteInstanceStarted,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self._require(spec.configuration, op, control, cleanup=False)
        if (
            spec != self.spec
            or self.ready != ready
            or self.started is not None
            or started.files != spec.configuration.files
        ):
            raise OwnershipConflict(
                "Original site startup changed fixed acquisition/files"
            )
        self.started = SiteInstanceStarted.model_validate(started)

    def verify_task(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> None:
        raise OwnershipConflict(
            "Native requests require the original current TaskSiteAuthority supplier"
        )

    def verify_closed(
        self,
        spec: SiteResourceSpec,
        attempt: SiteResourceAttempt,
        termination: ProcessTermination | None,
        step: SiteStepClosed | None,
        op: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        self._require(spec.configuration, op, control, cleanup=True)
        self._closing = True
        if (
            spec != self.spec
            or termination is None
            or termination.state != "reaped"
            or termination.cleanup_errors
            or step is None
            or step.target != attempt.target
            or (self.ready is not None and attempt.ready != self.ready)
        ):
            raise OwnershipConflict("Original site domain closure is unconfirmed")
        proof = self.owner.evidence.put(
            json.dumps(
                {
                    "schema_version": "claimed-site-disposition/1",
                    "token": spec.token.model_dump(mode="json"),
                    "node_root": spec.configuration.files.node_root,
                    "residual_files": "retained_private_no_reuse",
                    "step": step.model_dump(mode="json"),
                },
                sort_keys=True,
            ).encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="claimed-site-disposition/1",
                visibility="private",
                producer="claimed-site-owner",
            ),
            control=control,
        )
        return ClosureReceipt(
            token=spec.token,
            operation_id=op.operation_id,
            status="closed",
            evidence=(step.evidence, proof),
        )
