"""Navigation worker-local fixture: actual file restore, synthetic native services.

No source, task dispatch or physical writer authority is created by this fixture.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.tasks.navigation_lifecycle import (
    AdminNavigationLifecycle,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
    NavigationRecoverySnapshot,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    bind_admin_navigation,
)
from test_admin_state import (
    Commands as StateCommands,
    command_phase as state_command_phase,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_contents_program import (
    NAVIGATION_CONTENTS_PHP,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_contents import (
    NavigationContentsReply,
)
from test_admin_services import spec
from test_site_task_execution import request as original_request
from test_admin_description_inputs import reference
from test_slurm_commands import guard
from frontend_fixtures import frontend


def command_phase(argv: tuple[str, ...]) -> str:
    return (
        "navigation:contents"
        if NAVIGATION_CONTENTS_PHP in argv
        else state_command_phase(argv)
    )


class Commands(StateCommands):
    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        if NAVIGATION_CONTENTS_PHP not in argv:
            return super().run(argv, control)
        control.checkpoint()
        self.calls.append(argv)
        if self.fail == "navigation:contents":
            raise OSError("failed-navigation:contents")
        return (
            NavigationContentsReply(
                database_raw_sha256=argv[argv.index(NAVIGATION_CONTENTS_PHP) + 3],
                database_content_sha256="b" * 64,
                database_content_bytes=120,
                search_metadata_sha256="c" * 64,
                search_documents_sha256="d" * 64,
                search_documents=1,
                search_operation_mode="STOPPED",
                search_equivalence_metadata_sha256="e" * 64,
            )
            .model_dump_json()
            .encode()
        )


def request(
    contracts: Any, action: str = "snapshot", operation_id: str = "navigation-snapshot"
) -> SiteTaskRequest:
    native, ref, public = contracts[0]
    inputs = bind_admin_navigation(native, ref, public)
    old = original_request("snapshot", operation_id)
    return SiteTaskRequest(task=inputs.public_task.identity, binding_ref=old.binding_ref, operation=old.operation, action=action, snapshot_ref=None if action == "snapshot" else reference(b"pending snapshot", content_schema="admin-navigation-recovery/1"), private_input=NavigationExecutionInput(spec=inputs.private_spec).model_dump_json())  # type: ignore[arg-type]


def case(root: Path) -> tuple[AdminNavigationLifecycle, Commands]:
    path = root / "state/app/var/training-mail"
    path.mkdir(parents=True)
    (path / "message").write_bytes(b"original")
    commands = Commands()
    service = spec(root)

    def stop(control: OperationControl) -> Any:
        control.checkpoint()
        if commands.fail == "frontend":
            raise OSError("original frontend stop failed")
        return frontend(service)

    return AdminNavigationLifecycle(service, commands, stop), commands


def capture(
    worker: AdminNavigationLifecycle, contracts: Any
) -> tuple[SiteTaskRequest, EvidenceRef]:
    first = request(contracts)
    result = worker.execute_task(first, control=guard())
    saved = NavigationRecoverySnapshot.model_validate_json(result.private_result)
    assert saved.request == first
    return first, reference(
        result.private_result.encode(), content_schema=saved.schema_version
    )


def prepared(worker: AdminNavigationLifecycle, contracts: Any) -> SiteTaskRequest:
    original, ref = capture(worker, contracts)
    current = original.model_copy(
        update={
            "action": "prepare",
            "snapshot_ref": ref,
            "operation": original.operation.model_copy(
                update={"operation_id": "navigation-prepare"}
            ),
        }
    )
    worker.execute_task(current, control=guard())
    return current


def restore(parent: SiteTaskRequest, ref: EvidenceRef | None) -> SiteTaskRequest:
    return parent.model_copy(
        update={
            "action": "restore",
            "snapshot_ref": ref,
            "operation": parent.operation.cleanup(
                "navigation-restore", now=datetime.now(timezone.utc), seconds=30
            ),
        }
    )
