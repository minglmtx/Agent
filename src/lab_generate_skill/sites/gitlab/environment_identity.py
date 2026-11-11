"""Pure original physical GitLab identity checks shared by explicit families."""

import hashlib
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceContext
from lab_generate_skill.domain.native_private_json import NativePrivateJsonProfile
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from .snapshot import GitlabSnapshot
from .image import GITLAB_IMAGE_SHA
from .state_policy import ENVIRONMENT_RESET_CHECKS


def original_environment(
    site: SiteResourceSpec,
    started: SiteResourceStarted,
    state: GitlabSnapshot,
    context: SitePrivateEvidenceContext,
    profile: NativePrivateJsonProfile,
    label: str,
) -> None:
    config, service = site.configuration, state.service
    if config.private_evidence is None or config.private_evidence.profile != profile:
        raise OwnershipConflict(label + " environment changed declared native profile")
    if (
        config.site_id != "gitlab"
        or service.files != config.files
        or service.apptainer != config.apptainer
        or config.files.image.sha256 != GITLAB_IMAGE_SHA
        or started.instance.files != config.files
        or service.endpoint != started.instance.endpoint
        or (service.ports.web, service.ports.metrics) != started.instance.ports
        or context.configuration_sha256
        != hashlib.sha256(config.model_dump_json().encode()).hexdigest()
        or context.token != site.token
        or context.instance != started.instance
        or context.owner_guard != started.ready.worker.owner_guard
        or context.owner_guard.controller != site.slurm.parent.writer
    ):
        raise OwnershipConflict(
            label + " environment lost original image/site/worker/ports"
        )
    installed = started.ready.worker.installed_sources
    if (installed.release_id, installed.manifest_sha256, installed.executable) != (
        config.installation.manifest.release_id,
        config.installation.manifest_ref.sha256,
        config.installation.python_executable,
    ):
        raise OwnershipConflict(
            label + " environment changed original installed release"
        )
    worker = context.owner_guard.worker
    for stopped in state.original_stop.namespaces:
        for process in (stopped.original.launcher, stopped.original.init):
            if (process.node_id, process.boot_id) != (
                worker.node_id,
                worker.boot_id,
            ) or process.start_ticks < worker.start_ticks:
                raise OwnershipConflict(
                    label + " snapshot changed original worker host/boot/order"
                )


def original_environment_recovery(
    recovery: RecoveryPlan, scope: StateScope, spec_ref: EvidenceRef, label: str
) -> None:
    if (
        recovery.owner,
        recovery.attempt_id,
        recovery.baseline_ref,
        recovery.restore_component_id,
        recovery.restore_component_version,
        recovery.state_coverage,
    ) != (
        scope.owner,
        None,
        spec_ref,
        "gitlab-services",
        "1",
        ENVIRONMENT_RESET_CHECKS,
    ):
        raise ValueError(
            label + " environment recovery omits original six-service resume"
        )
