"""One fixed measurement on original live Shopping; no resource or source grant."""

import math
from time import monotonic_ns
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from ..service_contract import ShoppingServiceSpec
from ..service_commands import container
from .navigation_database_contents import (
    NavigationDatabaseContents,
    ORIGINAL_IMAGE_SHA256,
)
from .navigation_database_program import DATABASE_CONTENTS


def capture_navigation_database(
    spec: ShoppingServiceSpec, commands: NativeCommands, control: OperationControl
) -> NavigationDatabaseContents:
    spec = ShoppingServiceSpec.model_validate(spec)
    if spec.files.image.sha256 != ORIGINAL_IMAGE_SHA256:
        raise ValueError("Original pinned Shopping image required before measurement")
    # Python monotonic_ns and PHP hrtime use the original Linux monotonic clock.
    # Pass the current operation's deadline, not a new per-table time budget.
    before = monotonic_ns()
    remaining = control.checkpoint()
    if (
        type(remaining) not in (int, float)
        or not math.isfinite(remaining)
        or not 0 < remaining <= 86400
    ):
        raise ValueError("Finite bounded original SQL measurement time required")
    deadline = before + int(remaining * 1_000_000_000)
    raw = commands.run(
        container(spec)
        + (
            "php",
            "-r",
            DATABASE_CONTENTS,
            spec.endpoint,
            str(spec.ports.search),
            str(deadline),
        ),
        control,
    )
    result: NavigationDatabaseContents | None = None
    try:
        result = NavigationDatabaseContents.model_validate_json(raw)
        result.require_service(spec)
        control.checkpoint()
        return result
    except BaseException as error:
        setattr(error, "shopping_navigation_database_raw_reply", raw)
        setattr(error, "shopping_navigation_database_contents", result)
        raise
