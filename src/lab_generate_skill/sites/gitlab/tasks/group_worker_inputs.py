"""Bind declared Group inputs to each original task call, before native effects."""

import hashlib
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from .group_request import task_input


def verify_group_worker_inputs(
    configuration: SiteWorkerConfiguration, request: SiteTaskRequest
) -> None:
    declared = configuration.gitlab_group_inputs
    if declared is None:
        return
    private = task_input(request)
    if (
        request.task != declared.scope.task
        or request.operation.attempt_id != declared.scope.attempt_id
        or private.native_contract_ref.sha256 != declared.native_contract_sha256
        or hashlib.sha256(request.private_input.encode()).hexdigest()
        != declared.private_input_sha256
    ):
        raise OwnershipConflict(
            "Group call changed original declared task/attempt/input"
        )
