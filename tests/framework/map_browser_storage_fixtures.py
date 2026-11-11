"""Real browser journal/CAS/files with explicitly simulated browser/kernel effects."""

from pathlib import Path
from lab_generate_skill.domain.lifecycle import ResourceOwner
from evidence_control_fixtures import EvidenceFixtureStore
from browser_worker_fixtures import configuration as base_configuration
from lab_generate_skill.domain.lifecycle import OperationContext
import hashlib
from lab_generate_skill.domain.map_browser_collection import (
    MapBrowserCollectionSpec,
    SOURCE_PATHS,
)
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from map_served_fixtures import originals
from typing import Any, Literal
import pytest
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.map_browser_inputs import MapBrowserInputs
from lab_generate_skill.domain.map_private_artifact import MapPrivateArtifactPlan
from lab_generate_skill.adapters.browsergym.storage_original import (
    OriginalBrowserAcquisitionReader,
)
from lab_generate_skill.adapters.map_artifacts.browser_access import (
    OriginalMapBrowserAccess,
)
from lab_generate_skill.adapters.map_artifacts.writer import MapArtifactWriter
from lab_generate_skill.adapters.slurm.linux_cgroups import KernelCgroupObservation
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
import lab_generate_skill.adapters.map_artifacts.browser_access as access
from browser_resource_fixtures import resource_case
from map_artifact_fixtures import case
from map_route_fixtures import selected_spec
from test_site_storage_admission import LiveGuard
from test_slurm_commands import guard


class BrowserFilesCase:
    def __init__(
        self,
        root: Path,
        patch: pytest.MonkeyPatch,
        *,
        owner: ResourceOwner | None = None,
        store: EvidenceFixtureStore | None = None,
        workspace: Path | None = None,
    ) -> None:
        root.chmod(0o700)
        base = None
        if owner is not None:
            base = base_configuration()
            base = base.model_copy(
                update={
                    "spec": base.spec.model_copy(
                        update={
                            "scope": base.spec.scope.model_copy(update={"owner": owner})
                        }
                    )
                }
            )
        self.resource = resource_case(root, patch, config=base, store=store)
        template, _ = case(root)
        scope = template.plan.scope.model_copy(
            update={"owner": self.resource.spec.token.owner}
        )
        self.plan = MapPrivateArtifactPlan.model_validate(
            template.plan.model_copy(
                update={
                    "scope": scope,
                    "workspace_root": str(workspace or root),
                    "token": self.resource.spec.token,
                }
            )
        )
        template.plan = self.plan
        collection = collection_spec(root, self.resource.op)
        cfg = self.resource.spec.configuration
        config = BrowserWorkerConfiguration.model_validate(
            cfg.model_copy(
                update={
                    "spec": selected_spec(template, "http://127.0.0.1:8000/"),
                    "map_inputs": MapBrowserInputs(
                        plan=self.plan,
                        evidence_root=str((workspace or root) / "evidence"),
                        resource_journal_root=str(root / "journal"),
                        collection=collection,
                    ),
                }
            )
        )
        self.resource.spec = BrowserResourceSpec.model_validate(
            self.resource.spec.model_copy(update={"configuration": config})
        )
        self.configuration = config
        self.reader = OriginalBrowserAcquisitionReader()
        self.participant: Literal["worker", "controller"] = "worker"
        self.member_change: dict[str, Any] = {}
        self.identity_changed = False

        def identity() -> Any:
            original = self.reader.read(self.configuration, guard())
            value = original.acquired.details.prepared.owner_guard
            observed = (
                value.worker if self.participant == "worker" else value.controller
            )
            return (
                observed.model_copy(update={"start_ticks": observed.start_ticks + 1})
                if self.identity_changed
                else observed
            )

        def kernel(*args: Any) -> KernelCgroupObservation:
            original = self.reader.read(self.configuration, guard())
            member = (
                original.acquired.details.prepared.step.controller.target.worker
                if self.participant == "worker"
                else original.spec.slurm.parent
            )
            member = type(member).model_validate(
                {**member.model_dump(), **self.member_change}
            )
            return KernelCgroupObservation(member, KernelCapture((), ()))

        patch.setattr(access, "current_process_identity", identity)
        patch.setattr(access, "observe_current_cgroup", kernel)

    def authority(self) -> OriginalMapBrowserAccess:
        value = self.reader.read(
            self.configuration, guard()
        ).acquired.details.prepared.owner_guard
        return OriginalMapBrowserAccess(
            self.configuration,
            self.participant,
            self.reader,
            LiveGuard(value) if self.participant == "worker" else None,
        )

    def writer(self, authority: OriginalMapBrowserAccess) -> MapArtifactWriter:
        return MapArtifactWriter(self.plan, Path(self.plan.workspace_root), authority)


def collection_spec(
    root: Path, operation: OperationContext, tile_origin: str = "http://127.0.0.1:8001"
) -> MapBrowserCollectionSpec:
    source_root = root / "original-sources"
    pins = []
    data = originals()
    for path in sorted(SOURCE_PATHS):
        target = source_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = data[target.name]
        target.write_bytes(raw)
        target.chmod(0o444)
        pins.append(
            ReleaseFile(
                path=path,
                sha256=hashlib.sha256(raw).hexdigest(),
                size_bytes=len(raw),
                executable=False,
            )
        )
    collection = MapBrowserCollectionSpec(
        operation=operation,
        lifetime_operation=operation.model_copy(
            update={
                "operation_id": "map-collection-lifetime",
                "parent_operation_id": operation.operation_id,
            }
        ),
        original_sources=ReleaseArtifact(
            artifact_id="original-map-scripts",
            root=str(source_root),
            files=tuple(pins),
        ),
        tile_origin=tile_origin,
        max_requests=16,
    )
    return collection
