"""Measure original held stopped copy; no live reset, source or resume grant."""

import hashlib
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from ..snapshot import ShoppingSnapshot, require_stop
from ..service_commands import container
from .navigation_database_contents import ORIGINAL_IMAGE_SHA256
from .navigation_file_contents import NavigationFileContents, NavigationFileReply
from .navigation_file_program import FILE_CONTENTS


def capture_navigation_files(
    snapshot: ShoppingSnapshot, commands: NativeCommands, control: OperationControl
) -> NavigationFileContents:
    snapshot = ShoppingSnapshot.model_validate(snapshot)
    require_stop(snapshot.original_stop)
    spec = snapshot.service
    if spec.files.image.sha256 != ORIGINAL_IMAGE_SHA256:
        raise ValueError("Original pinned Shopping image required before measurement")
    control.checkpoint()
    base = container(spec, seeded=False, snapshot=True)
    # This consumer never needs to write either the stopped copy or live tree.
    base = tuple(
        (
            x + ":ro"
            if x
            in (spec.snapshot_root + ":/snapshot", spec.files.state_root + ":/state")
            else x
        )
        for x in base
    )
    ports = spec.ports
    raw = commands.run(
        base
        + (
            "php",
            "-r",
            FILE_CONTENTS,
            snapshot.inventory.model_dump_json(),
            *(
                str(x)
                for x in (ports.database, ports.redis, ports.search, ports.transport)
            ),
        ),
        control,
    )
    result: NavigationFileContents | None = None
    try:
        reply = NavigationFileReply.model_validate_json(raw)
        result = NavigationFileContents(
            snapshot_sha256=hashlib.sha256(
                snapshot.model_dump_json().encode()
            ).hexdigest(),
            measured=reply,
        )
        result.require_snapshot(snapshot)
        control.checkpoint()
        return result
    except BaseException as error:
        setattr(error, "shopping_navigation_files_raw_reply", raw)
        setattr(error, "shopping_navigation_files_contents", result)
        raise
