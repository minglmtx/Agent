"""Pure wiring of the worker-local Admin instance; construction has no effects.

Caller must persist/authorize the exact plan before prepare and keep this worker
inside its original supervised resource. No default authority or legacy entry.
"""

from pathlib import Path
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_services import NativeServices
from lab_generate_skill.adapters.sites.files import NodeSiteFiles
from lab_generate_skill.adapters.network.loopback_ports import LoopbackPorts
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from lab_generate_skill.sites.shopping_admin.instance import AdminInstance
from lab_generate_skill.sites.shopping_admin.instance_contract import AdminInstancePlan


def build_admin_instance(plan: AdminInstancePlan) -> AdminInstance:
    def services(log_root: str, control: OperationControl) -> NativeServices:
        control.checkpoint()
        return LocalNativeServices(Path(log_root))

    return AdminInstance(
        plan,
        files=NodeSiteFiles(),
        ports=LoopbackPorts(
            required_prefix=(
                ()
                if plan.navigation_origin is None
                else (plan.navigation_origin.web_port,)
            )
        ),
        commands=CheckedNativeCommands(ProcessRunner(max_output_bytes=256 * 1024)),
        services=services,
    )
