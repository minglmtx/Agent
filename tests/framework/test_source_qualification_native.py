"""Original pending native bytes/order on explicit synthetic site/kernel premises."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.adapters.sites.source_qualification_native import (
    SourceQualificationNativeAuthority,
    PendingQualificationNative,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.native_request_rules import (
    NavigationNativeRequestChecks,
)
from map_task_preparation_port_fixtures import preparation_case
from site_instance_fixtures import node_path as node_path


def test_original_source_native_snapshot_prepare_once_and_restore_requires_closed_browser(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with preparation_case(node_path, monkeypatch, "125732d3658ab4daee02") as p:
        p.acquire()
        p.prepare()
        c, state = p.original, p.preparation.state

        class UnitSourceOwner(OriginalSourceQualificationOwner):
            def require_caller(
                self, op: OperationContext, control: OperationControl
            ) -> None:
                control.checkpoint()
                assert (op.run_id, op.owner_id) == (
                    self.scope.owner.run_id,
                    self.scope.owner.owner_id,
                )

        owner = UnitSourceOwner(
            c.scope,
            c.resource.spec.slurm.execution,
            c.resource.spec.slurm.parent,
            c.resource.evidence,
        )
        pending: PendingQualificationNative | None = None
        authority = SourceQualificationNativeAuthority(
            owner,
            c.resource.spec,
            c.resource.op,
            c.resource.journal,
            lambda: pending,
            NavigationNativeRequestChecks(),
        )
        assert state.snapshot_request is not None and state.prepare_request is not None
        assert state.snapshot_ref is not None
        binding = p.source.native.binding
        before = len(p.requests)

        def select(request: SiteTaskRequest) -> PendingQualificationNative:
            ref = c.resource.evidence.put(
                request.model_dump_json().encode(),
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema=request.schema_version,
                    visibility="private",
                    producer="source-qualification-native-v1",
                ),
                c.resource.controls.bind(request.operation),
            )
            return PendingQualificationNative(
                request,
                ref,
                binding,
                snapshot_request=state.snapshot_request,
                snapshot_ref=state.snapshot_ref,
            )

        # These are original persisted fixture RPCs. Verifying their permission
        # invokes no native RPC and cannot repeat preparation in the worker.
        with pytest.raises(DispatchAlreadyCommitted):
            authority.verify_task(
                c.configuration,
                state.prepare_request,
                c.resource.controls.bind(state.prepare_request.operation),
            )
        pending = select(state.snapshot_request)
        wrong = state.snapshot_request.model_copy(
            update={
                "binding_ref": state.prepare_request.binding_ref.model_copy(
                    update={"producer": "foreign"}
                )
            }
        )
        with pytest.raises(OwnershipConflict):
            authority.verify_task(
                c.configuration, wrong, c.resource.controls.bind(wrong.operation)
            )
        authority.verify_task(
            c.configuration,
            state.snapshot_request,
            c.resource.controls.bind(state.snapshot_request.operation),
        )
        with pytest.raises(DispatchAlreadyCommitted):
            authority.verify_task(
                c.configuration,
                state.snapshot_request,
                c.resource.controls.bind(state.snapshot_request.operation),
            )
        pending = select(state.prepare_request)
        authority.verify_task(
            c.configuration,
            state.prepare_request,
            c.resource.controls.bind(state.prepare_request.operation),
        )
        restore = SiteTaskRequest(
            task=c.scope.task,
            binding_ref=state.prepare_request.binding_ref,
            operation=state.prepare_request.operation.cleanup(
                "source-restore-probe",
                now=state.prepare_request.operation.deadline,
                seconds=30,
            ),
            action="restore",
            snapshot_ref=state.snapshot_ref,
            private_input=state.prepare_request.private_input,
        )
        pending = select(restore)
        with pytest.raises(OwnershipConflict, match="closed observation browser"):
            authority.verify_task(
                c.configuration, restore, c.resource.controls.bind(restore.operation)
            )
        assert len(p.requests) == before
