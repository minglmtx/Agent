"""Source-only site permissions on the existing independent physical observer.

Concrete site checks approve only their exact original declaration. Native
requests still require a once-bound source qualification supplier. This grants
no Actor dispatch, task claim, formal construction or training permission.
"""

import json
import os
from pathlib import Path
from typing import Literal
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
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


class SourceSiteLifecycleAuthority:
    def __init__(
        self,
        owner: OriginalSourceQualificationOwner,
        spec: SiteResourceSpec,
        acquisition: OperationContext,
    ) -> None:
        if not isinstance(owner, OriginalSourceQualificationOwner):
            raise TypeError("Original source-only physical owner required")
        self.owner, self.spec, self.acquisition = (
            owner,
            SiteResourceSpec.model_validate(spec),
            OperationContext.model_validate(acquisition),
        )
        self.spec.check_operation(self.acquisition, "execute")
        self.ready: SiteResourceReady | None = None
        self.started: SiteInstanceStarted | None = None
        self._spawn = self._closing = False
        self._configured = self._start_attempted = False
        self._close_attempted = False
        if (
            self.spec.token.owner != owner.scope.owner
            or self.spec.configuration.site_id != owner.scope.task.site
            or self.spec.slurm.execution != owner.execution
            or self.spec.slurm.parent != owner.controller
        ):
            raise OwnershipConflict("Original current task/site/controller required")
        self.verify_source_declaration()

    def verify_source_declaration(self) -> None:
        """Concrete site binding must approve its exact source-only declaration."""
        raise NotImplementedError("A concrete original source declaration is mandatory")

    def _require(
        self,
        configuration: SiteWorkerConfiguration,
        op: OperationContext,
        control: OperationControl,
        *,
        cleanup: bool,
    ) -> None:
        if configuration != self.spec.configuration:
            raise OwnershipConflict("Source site changed original configuration")
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
        self.owner.require_caller(op, control)
        self._spawn = True
        self._require(spec.configuration, op, control, cleanup=False)
        self.verify_source_declaration()
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
        elif not self._spawn:
            raise OwnershipConflict("Original source worker spawn admission required")
        elif phase == "configure":
            if self._configured:
                raise OwnershipConflict("Original source configuration is one-shot")
            self._configured = True
        else:
            if self.ready is None or self.started is not None or self._start_attempted:
                raise OwnershipConflict(
                    "Original source site start is one-shot after acquisition"
                )
            self._start_attempted = True

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
            or not self._spawn
            or not self._configured
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
            or not self._start_attempted
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
        if self._close_attempted:
            raise OwnershipConflict("Original source site close is one-shot")
        self._require(spec.configuration, op, control, cleanup=True)
        self._close_attempted = self._closing = True
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
                    "schema_version": "source-qualification-site-disposition/1",
                    "token": spec.token.model_dump(mode="json"),
                    "node_root": spec.configuration.files.node_root,
                    "residual_files": "retained_private_no_reuse",
                    "step": step.model_dump(mode="json"),
                },
                sort_keys=True,
            ).encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="source-qualification-site-disposition/1",
                visibility="private",
                producer="source-qualification-site-owner",
            ),
            control=control,
        )
        return ClosureReceipt(
            token=spec.token,
            operation_id=op.operation_id,
            status="closed",
            evidence=(step.evidence, proof),
        )
