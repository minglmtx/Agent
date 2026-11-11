"""Read actual complete original navigation contents; never grants permission."""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from ..state_contract import AdminStateSnapshot
from ..service_commands import container
from .navigation_contents_program import NAVIGATION_CONTENTS_PHP
from .navigation_equivalence_contents import (
    NavigationEquivalenceContents,
    NavigationEquivalenceContents as NavigationContents,
    NavigationEquivalenceReply,
    NavigationEquivalenceReply as NavigationContentsReply,
)

__all__ = [
    "NavigationContents",
    "NavigationContentsReply",
    "measure_navigation_contents",
]


def measure_navigation_contents(
    snapshot: AdminStateSnapshot, commands: NativeCommands, control: OperationControl
) -> NavigationEquivalenceContents:
    snapshot = AdminStateSnapshot.model_validate(snapshot)
    control.checkpoint()
    service = snapshot.plan.service
    expected = snapshot.search.model_dump_json(exclude={"schema_version", "service"})
    raw = commands.run(
        container(service)
        + (
            "php",
            "-r",
            NAVIGATION_CONTENTS_PHP,
            str(service.ports.search),
            str(control.checkpoint()),
            snapshot.database.sha256,
            str(snapshot.database.size_bytes),
            expected,
            service.admin_url,
        ),
        control,
    )
    result: NavigationEquivalenceContents | None = None
    try:
        reply = NavigationEquivalenceReply.model_validate_json(raw)
        if raw != reply.model_dump_json().encode():
            raise ValueError("Noncanonical navigation contents reply")
        result = NavigationEquivalenceContents(
            snapshot_sha256=snapshot.digest,
            image_sha256=service.layout.image_sha256,
            measured=reply,
            artifacts=tuple(
                zip(snapshot.artifacts.layout.paths, snapshot.artifacts.tree_sha256)
            ),
        )
        result.require_snapshot(snapshot)
        control.checkpoint()
        return result
    except BaseException as error:
        setattr(error, "admin_navigation_contents_raw_reply", raw)
        setattr(error, "admin_navigation_contents", result)
        raise
