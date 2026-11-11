"""Fixed original Reddit native3 and shared private evidence assembly."""

import sys
import time
from pathlib import Path
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.ports.site_storage import SiteWorkerGuard
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from lab_generate_skill.adapters.sites.files import NodeSiteFiles
from lab_generate_skill.adapters.sites.reddit_read_inputs import NativeReadInputs
from lab_generate_skill.adapters.network.loopback_ports import LoopbackPorts
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.native_input_commands import (
    CheckedNativeInputCommands,
)
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from lab_generate_skill.adapters.browsergym.login_catalog import reddit_login
from lab_generate_skill.sites.reddit.instance import RedditInstance
from lab_generate_skill.sites.reddit.worker_instance import RedditWorkerInstance
from lab_generate_skill.sites.reddit.progress import RedditPhase
from .worker_private_artifacts import WorkerPrivateArtifacts


def reddit_worker_progress(phase: RedditPhase) -> None:
    if not isinstance(phase, RedditPhase):
        raise ValueError("Only fixed Reddit diagnostic phases allowed")
    try:
        sys.stderr.write(f"REDDIT_PHASE {phase.value} {time.monotonic():.6f}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def build_reddit_worker(
    configuration: SiteWorkerConfiguration, guard: SiteWorkerGuard
) -> RedditWorkerInstance:
    configuration = SiteWorkerConfiguration.model_validate(configuration)

    def services(root: str, control: OperationControl) -> QuiescentNativeServices:
        control.checkpoint()
        return LocalNativeServices(Path(root))

    def username(control: OperationControl) -> str:
        return reddit_login(control)[0]

    instance = RedditInstance(
        configuration.files,
        files=NodeSiteFiles(),
        ports=LoopbackPorts(),
        commands=CheckedNativeCommands(ProcessRunner(max_output_bytes=256 * 1024)),
        services=services,
        progress=reddit_worker_progress,
    )
    return RedditWorkerInstance(
        configuration,
        instance,
        WorkerPrivateArtifacts(configuration, guard),
        CheckedNativeInputCommands(ProcessRunner(max_output_bytes=64 * 1024**2)),
        NativeReadInputs(str(Path(configuration.files.node_root) / "native-input")),
        username,
    )
