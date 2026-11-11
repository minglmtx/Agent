"""Fixed GitLab/native/storage assembly; outer original resource owns effects."""

import os
import pwd
import sys
import time
from pathlib import Path
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.ports.site_storage import SiteWorkerGuard
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from lab_generate_skill.adapters.sites.files import NodeSiteFiles
from lab_generate_skill.adapters.network.loopback_ports import LoopbackPorts
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.native_input_commands import (
    CheckedNativeInputCommands,
)
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from lab_generate_skill.adapters.browsergym.login_catalog import gitlab_login
from lab_generate_skill.sites.gitlab.instance import GitlabInstance
from lab_generate_skill.sites.gitlab.worker_instance import GitlabWorkerInstance
from lab_generate_skill.sites.gitlab.progress import GitlabPhase
from .worker_private_artifacts import WorkerPrivateArtifacts
from .gitlab_group_lifecycle import build_group_lifecycle


def gitlab_worker_progress(phase: GitlabPhase) -> None:
    if not isinstance(phase, GitlabPhase):
        raise ValueError("Only fixed GitLab diagnostic phases allowed")
    try:
        sys.stderr.write(f"GITLAB_PHASE {phase.value} {time.monotonic():.6f}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def build_gitlab_worker(
    configuration: SiteWorkerConfiguration, guard: SiteWorkerGuard
) -> GitlabWorkerInstance:
    configuration = SiteWorkerConfiguration.model_validate(configuration)

    def services(root: str, control: OperationControl) -> QuiescentNativeServices:
        control.checkpoint()
        return LocalNativeServices(Path(root))

    def username(control: OperationControl) -> str:
        return gitlab_login(control)[0]

    instance = GitlabInstance(
        configuration.files,
        database_peer_user=pwd.getpwuid(os.getuid()).pw_name,
        files=NodeSiteFiles(),
        ports=LoopbackPorts(
            required_prefix=(
                (configuration.gitlab_group_inputs.origin.web_port,)
                if configuration.gitlab_group_inputs is not None
                else ()
            )
        ),
        commands=CheckedNativeCommands(ProcessRunner(max_output_bytes=256 * 1024)),
        services=services,
        progress=gitlab_worker_progress,
    )
    return GitlabWorkerInstance(
        configuration,
        instance,
        WorkerPrivateArtifacts(configuration, guard),
        CheckedNativeInputCommands(ProcessRunner(max_output_bytes=64 * 1024 * 1024)),
        username,
        group_lifecycle_factory=build_group_lifecycle,
    )
