"""Original worker measurement around its existing single stopped-tree snapshot.

The enclosing registered native request owns authority and writer exclusion.
No source grant, additional snapshot, service restart, retry or resume is added.
"""

import hashlib
from lab_generate_skill.ports.lifecycle import OperationControl
from ..instance import ShoppingInstance
from ..snapshot import ShoppingSnapshot
from ..services import SERVICE_NAMES
from .navigation_contents import NavigationBeforeContents, NavigationContents
from .navigation_database_capture import capture_navigation_database
from .navigation_search_capture import capture_navigation_search
from .navigation_file_capture import capture_navigation_files


def before_navigation_snapshot(
    instance: ShoppingInstance, control: OperationControl
) -> NavigationBeforeContents:
    instance._owner()
    if (
        instance.state != "ready"
        or instance.spec is None
        or instance.snapshot is not None
        or not instance.generations
    ):
        raise RuntimeError("Contents require original pre-snapshot Shopping worker")
    generation = instance.generations[-1]
    generation.services.require_running()
    if tuple(x.service for x in generation.pins) != SERVICE_NAMES:
        raise RuntimeError("Original Shopping writer pins required")
    database = capture_navigation_database(instance.spec, instance.commands, control)
    search = None
    try:
        search = capture_navigation_search(instance.spec, instance.commands, control)
        generation.services.require_running()
        result = NavigationBeforeContents(
            service=instance.spec,
            original_pins=generation.pins,
            database=database,
            search=search,
        )
        control.checkpoint()
        return result
    except BaseException as error:
        setattr(error, "shopping_navigation_database_before", database)
        setattr(error, "shopping_navigation_search_before", search)
        raise


def after_navigation_snapshot(
    instance: ShoppingInstance,
    snapshot: ShoppingSnapshot,
    before: NavigationBeforeContents,
    control: OperationControl,
) -> NavigationContents:
    instance._owner()
    snapshot = ShoppingSnapshot.model_validate(snapshot)
    before = NavigationBeforeContents.model_validate(before)
    if (
        instance.state != "snapshotted"
        or instance.snapshot != snapshot
        or instance.spec != snapshot.service
    ):
        raise RuntimeError("Original completed Shopping snapshot/restart required")
    generation = instance.generations[-1]
    generation.services.require_running()
    database = None
    search = None
    files = None
    try:
        database = capture_navigation_database(
            snapshot.service, instance.commands, control
        )
        search = capture_navigation_search(snapshot.service, instance.commands, control)
        files = capture_navigation_files(snapshot, instance.commands, control)
        generation.services.require_running()
        result = NavigationContents(
            snapshot_sha256=hashlib.sha256(
                snapshot.model_dump_json().encode()
            ).hexdigest(),
            before=before,
            restarted_pins=generation.pins,
            database=database,
            search=search,
            files=files,
        )
        result.require_snapshot(snapshot)
        control.checkpoint()
        return result
    except BaseException as error:
        setattr(error, "shopping_navigation_contents_snapshot", snapshot)
        setattr(error, "shopping_navigation_before_contents", before)
        setattr(error, "shopping_navigation_database_after", database)
        setattr(error, "shopping_navigation_search_after", search)
        setattr(error, "shopping_navigation_files_after", files)
        raise
