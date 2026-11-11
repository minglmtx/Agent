"""Declare current Map workers from an explicit original attempt scope.

Pure composition: no acquisition, CAS, source admission or request permission.
The caller supplies the original resource token and qualified runtime inputs.
"""

import hashlib
from pathlib import Path
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeInputs
from lab_generate_skill.domain.map_worker_inputs import MapWorkerInputs
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.map_origin import MapOriginPolicy
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from lab_generate_skill.sites.map.tasks.overlay_spec import NativeOverlaySpec


def map_task_configuration(
    runtime: MapRuntimeInputs,
    private: NativeOverlaySpec | NavigationSpec,
    scope: StateScope,
    token: AllocationToken,
    installation: ReleaseInstallation,
    *,
    origin: MapOriginPolicy | None,
    evidence_root: Path,
    resource_journal_root: Path,
    artifact_root: Path,
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
) -> SiteWorkerConfiguration:
    if not all(
        (
            isinstance(runtime, MapRuntimeInputs),
            isinstance(scope, StateScope),
            isinstance(token, AllocationToken),
            isinstance(installation, ReleaseInstallation),
            isinstance(private, (NativeOverlaySpec, NavigationSpec)),
            all(
                isinstance(p, Path)
                for p in (evidence_root, resource_journal_root, artifact_root)
            ),
        )
    ):
        raise TypeError(
            "Original typed Map runtime/task/scope/token/installation and paths required"
        )
    runtime = MapRuntimeInputs.model_validate(runtime)
    scope = StateScope.model_validate(scope)
    token = AllocationToken.model_validate(token)
    installation = ReleaseInstallation.model_validate(installation)
    private = type(private).model_validate(private)
    if (
        scope.owner != token.owner
        or scope.task != private.task
        or token.scope != "batch"
        or token.resource_kind != "site"
        or token.expected_resource_id != runtime.files.instance_id
        or (token.provider_id, token.provider_version) != ("fixed-site-worker", "6")
    ):
        raise OwnershipConflict(
            "Map declaration changed original attempt, task or outer site allocation"
        )
    values = dict(
        runtime=runtime,
        scope=scope,
        private_input_sha256=hashlib.sha256(
            private.model_dump_json().encode()
        ).hexdigest(),
        evidence_root=str(evidence_root),
        resource_journal_root=str(resource_journal_root),
        artifact_root=str(artifact_root),
        max_files=max_files,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
    )
    inputs: MapWorkerInputs | MapNavigationWorkerInputs
    if isinstance(private, NavigationSpec):
        if not isinstance(origin, MapOriginPolicy):
            raise TypeError("Explicit navigation origin policy required")
        inputs = MapNavigationWorkerInputs.model_validate(
            {
                **values,
                "origin": origin,
                "native_contract_sha256": private.native_contract_ref.sha256,
            }
        )
    else:
        if origin is not None:
            raise ValueError("Navigation origin policy is not a MapData declaration")
        inputs = MapWorkerInputs.model_validate(values)
    return SiteWorkerConfiguration(
        site_id="map",
        token=token,
        files=runtime.files,
        installation=installation,
        apptainer="/usr/bin/apptainer",
        private_evidence=None,
        map_inputs=inputs,
    )
