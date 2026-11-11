"""Pure original Map state-file declaration; deriving a plan grants no access."""

import hashlib
from pathlib import PurePosixPath
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.map_private_artifact import (
    MapPrivateArtifactPlan,
    MapArtifactPlan,
)
from lab_generate_skill.domain.map_navigation_artifact import MapNavigationArtifactPlan
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.errors import OwnershipConflict


def original_site_plan(
    configuration: SiteWorkerConfiguration, request: SiteTaskRequest
) -> MapArtifactPlan:
    configuration = SiteWorkerConfiguration.model_validate(configuration)
    request = SiteTaskRequest.model_validate(request)
    request.check_site(configuration)
    inputs = configuration.map_inputs
    if inputs is None or (
        request.task != inputs.scope.task
        or request.operation.attempt_id != inputs.scope.attempt_id
        or hashlib.sha256(request.private_input.encode()).hexdigest()
        != inputs.private_input_sha256
    ):
        raise OwnershipConflict(
            "Map artifact changed frozen source/attempt/private input"
        )
    declaration = dict(
        scope=inputs.scope,
        token=configuration.token,
        producer="native_database",
        workspace_root=configuration.files.workspace_root,
        private_root=str(
            PurePosixPath(inputs.artifact_root) / ("state-" + request.digest)
        ),
        artifact_id="map-state-" + request.digest,
        max_files=inputs.max_files,
        max_file_bytes=inputs.max_file_bytes,
        max_total_bytes=inputs.max_total_bytes,
    )
    if isinstance(inputs, MapNavigationWorkerInputs):
        return MapNavigationArtifactPlan.model_validate(
            {**declaration, "native_contract_sha256": inputs.native_contract_sha256}
        )
    return MapPrivateArtifactPlan.model_validate(declaration)
