"""Inert Map declarations for original worker/storage boundary acceptance.

All native inputs are intentionally absent. No production asset publication is
read; these declarations cannot authorize a service or task.
"""

import hashlib
from pathlib import Path
from lab_generate_skill.domain.map_runtime_inputs import (
    IMAGE_PINS,
    MapRuntimeImage,
    MapRuntimeInputs,
    MapRuntimeTree,
)
from lab_generate_skill.domain.map_worker_inputs import MapWorkerInputs
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.sites.map.tasks.overlay_spec import NativeOverlaySpec
from site_worker_fixtures import configuration
from test_core_contracts import reference


def missing_input_configuration(
    installation: ReleaseInstallation, *, job_id: str, root: Path, parent: Path
) -> SiteWorkerConfiguration:
    base = configuration(installation, job_id=job_id)
    images = tuple(
        MapRuntimeImage.model_validate(
            dict(
                role=role,
                source_path=str(root / "absent-inputs" / (role + ".sif")),
                file=ReleaseFile(
                    path=role + ".sif", sha256=sha, size_bytes=size, executable=False
                ),
            )
        )
        for role, (sha, size) in IMAGE_PINS.items()
    )
    trees = tuple(
        MapRuntimeTree.model_validate(
            dict(
                role=role,
                source_root=str(root / "absent-inputs" / (role + "-tree")),
                inventory_path=str(root / (role + "-inventory.json")),
                inventory=ReleaseFile(
                    path=role + "-inventory.json",
                    sha256="0" * 64,
                    size_bytes=1,
                    executable=False,
                ),
            )
        )
        for role in ("app", "search", "routing", "tiles", "frontend")
    )
    web = next(i for i in images if i.role == "web")
    files = SiteFilesPlan(
        instance_id=base.token.expected_resource_id,
        workspace_root=str(root),
        source_path=web.source_path,
        node_root=str(parent / "instance"),
        image=web.file,
    )
    runtime = MapRuntimeInputs(
        files=files,
        images=images,
        trees=trees,
        publication_path=str(root / "missing-publication.json"),
        publication=ReleaseFile(
            path="missing-publication.json",
            sha256="0" * 64,
            size_bytes=1,
            executable=False,
        ),
        publication_job_id="12345",
    )
    task = TaskIdentity(
        site="map",
        family="native_route_map_data",
        contract_version=1,
        split="train",
        task_id=runtime.selected_source,
        source_task_id=runtime.selected_source,
    )
    private = NativeOverlaySpec(
        task=task, native_contract_ref=reference("private", "map-native-contract/1")
    )
    return SiteWorkerConfiguration(
        site_id="map",
        token=base.token,
        files=files,
        installation=installation,
        apptainer="/usr/bin/apptainer",
        private_evidence=None,
        map_inputs=MapWorkerInputs(
            runtime=runtime,
            scope=StateScope(
                owner=base.token.owner,
                task=task,
                attempt_id="attempt",
                context_id="context",
            ),
            private_input_sha256=hashlib.sha256(
                private.model_dump_json().encode()
            ).hexdigest(),
            evidence_root=str(root / "evidence"),
            resource_journal_root=str(root / "journal"),
            artifact_root=str(root / "map-files"),
            max_files=100,
            max_file_bytes=256 * 1024**2,
            max_total_bytes=512 * 1024**2,
        ),
    )
