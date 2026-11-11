"""Assembly rejects another source reader/private receipt/full plan, before binding."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_artifacts.origin_authority import (
    OriginalMapOriginAuthority,
)
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.bootstrap.map_task_execution import (
    map_navigation_task_execution,
)
from lab_generate_skill.domain.map_origin import MapOriginPolicy
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.errors import OwnershipConflict
from map_navigation_group_cases import SOURCES
from map_task_execution_current_fixtures import current_map_execution_case
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard
import map_task_execution_current_fixtures as fixtures
from lab_generate_skill.application.construction_task_phase_source import (
    ConstructionTaskOriginSource,
)


@pytest.mark.parametrize("fault", ["wrong-read", "other-private", "other-source-plan"])
def test_parent_binds_same_complete_construction_before_current_native_supplier(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    seen: list[str] = []

    def checked(
        declarations: Any, resources: Any, authorities: Any, runtime: Any
    ) -> Any:
        plan = declarations.plan
        progress = runtime.construction.read(plan.read_operation)
        public = PublicConstructionContext.model_validate_json(
            runtime.evidence.read(progress.plan.public_context_ref, guard())
        )
        receipt_ref = progress.plan.context_receipt_ref
        contexts = runtime.construction.verifier.contexts
        if fault == "other-private":
            receipt = PublicContextReceipt.model_validate_json(
                runtime.evidence.read(receipt_ref, guard())
            )
            other = receipt.model_copy(
                update={
                    "operation": receipt.operation.model_copy(
                        update={"operation_id": "unit-other-parent-private-source"}
                    )
                }
            )
            receipt_ref = contexts.publish_context(other, other.operation)
            assert receipt_ref != progress.plan.context_receipt_ref
            assert (
                contexts.load_context(
                    receipt_ref, plan.read_operation
                ).public_context_ref
                == progress.plan.public_context_ref
            )
        policy = MapOriginPolicy(
            mode="frozen_context",
            source_context_receipt_ref=receipt_ref,
            source_context_ref=progress.plan.public_context_ref,
            source_start_url=public.task.start_url,
        )
        data = resources.site_spec.model_dump()
        data["configuration"]["map_inputs"]["origin"] = policy.model_dump()
        spec = SiteResourceSpec.model_validate(data)
        read = (
            plan.read_operation.model_copy(update={"operation_id": "unit-other-read"})
            if fault == "wrong-read"
            else plan.read_operation
        )
        parent = OriginalMapOriginAuthority(
            contexts=contexts,
            evidence=runtime.evidence,
            source=ConstructionTaskOriginSource(runtime.construction),
            read_operation=read,
        )
        if fault == "other-source-plan":

            class DifferentProof:
                def verify_source(self, op: Any) -> Any:
                    return progress.model_copy(
                        update={
                            "plan": progress.plan.model_copy(
                                update={
                                    "retrieval_ref": progress.plan.retrieval_ref.model_copy(
                                        update={"sha256": "f" * 64}
                                    )
                                }
                            )
                        }
                    )

            parent.source = ConstructionTaskOriginSource(DifferentProof())
        native = TaskSiteAuthority(
            spec,
            resources.native_source.acquisition,
            resources.native_source.source,
            origin=parent,
        )
        changed = replace(resources, site_spec=spec, native_source=native)
        with pytest.raises(
            OwnershipConflict,
            match="parent origin changed original construction source",
        ):
            map_navigation_task_execution(declarations, changed, authorities, runtime)
        assert native._native is None
        seen.append(fault)
        return map_navigation_task_execution(
            declarations, resources, authorities, runtime
        )

    monkeypatch.setattr(fixtures, "map_navigation_task_execution", checked)
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as c:
        assert seen == [fault] and c.p.requests == []
        assert c.handles.browser is None and c.native.loader.session.calls == 0
