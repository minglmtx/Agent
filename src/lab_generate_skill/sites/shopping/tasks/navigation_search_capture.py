"""Fixed original local search read; caller still owns writers and cleanup."""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from ..service_contract import ShoppingServiceSpec
from ..service_commands import container
from .navigation_database_contents import ORIGINAL_IMAGE_SHA256
from .navigation_search_contents import NavigationSearchContents
from .navigation_search_program import SEARCH_CONTENTS


def capture_navigation_search(
    spec: ShoppingServiceSpec, commands: NativeCommands, control: OperationControl
) -> NavigationSearchContents:
    spec = ShoppingServiceSpec.model_validate(spec)
    if spec.files.image.sha256 != ORIGINAL_IMAGE_SHA256:
        raise ValueError("Original pinned Shopping image required before measurement")
    remaining = control.checkpoint()
    if remaining <= 6:
        raise ValueError(
            "Search read requires execution and bounded scroll cleanup time"
        )
    raw = commands.run(
        container(spec)
        + ("php", "-r", SEARCH_CONTENTS, str(spec.ports.search), str(remaining)),
        control,
    )
    result: NavigationSearchContents | None = None
    try:
        result = NavigationSearchContents.model_validate_json(raw)
        result.require_service(spec)
        control.checkpoint()
        return result
    except BaseException as error:
        setattr(error, "shopping_navigation_search_raw_reply", raw)
        setattr(error, "shopping_navigation_search_contents", result)
        raise
