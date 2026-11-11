"""Explicit Shopping native wiring; outer registered resource owns all effects."""

from pathlib import Path
import sys
import time
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.shopping_navigation_origin import ShoppingCategoryOrigin
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from lab_generate_skill.adapters.sites.files import NodeSiteFiles
from lab_generate_skill.adapters.network.loopback_ports import LoopbackPorts
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from lab_generate_skill.sites.shopping.instance import ShoppingInstance
from lab_generate_skill.sites.shopping.progress import ShoppingPhase, ShoppingProgress


def shopping_worker_progress(phase: ShoppingPhase) -> None:
    if not isinstance(phase, ShoppingPhase):
        raise ValueError("Only fixed Shopping diagnostic phases allowed")
    try:
        sys.stderr.write(f"SHOPPING_PHASE {phase.value} {time.monotonic():.6f}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        # Diagnostics do not replace operation/cleanup errors or grant rights.
        pass


def build_shopping_instance(
    plan: SiteFilesPlan,
    *,
    progress: ShoppingProgress | None = None,
    origin: ShoppingCategoryOrigin | None = None,
) -> ShoppingInstance:
    def services(log_root: str, control: OperationControl) -> QuiescentNativeServices:
        control.checkpoint()
        return LocalNativeServices(Path(log_root))

    return ShoppingInstance(
        plan,
        files=NodeSiteFiles(),
        ports=LoopbackPorts(
            required_prefix=() if origin is None else (origin.web_port,)
        ),
        commands=CheckedNativeCommands(ProcessRunner(max_output_bytes=256 * 1024)),
        services=services,
        progress=progress,
    )
