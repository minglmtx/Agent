"""Verify exact publication and inventories before any large native staging.

This proves metadata identities, not all input bytes, runtime permission or site
acceptance. The original supervised worker must verify/copy every declared file.
"""

from pathlib import Path
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeInputs, TREE_ROLES
from lab_generate_skill.domain.map_runtime_inventory import MapRuntimeInventory
from lab_generate_skill.ports.lifecycle import OperationControl
from .metadata import object_json, read_pinned_bytes
from .inventory import parse_inventory


class PublishedMapInputs:
    def read(
        self, plan: MapRuntimeInputs, control: OperationControl
    ) -> tuple[MapRuntimeInventory, ...]:
        plan = MapRuntimeInputs.model_validate(plan)
        receipt = object_json(
            read_pinned_bytes(Path(plan.publication_path), plan.publication, control)
        )
        if (
            receipt.get("passed") is not True
            or receipt.get("job_id") != plan.publication_job_id
        ):
            raise ValueError("Original successful publication identity required")
        for field in (
            "source_deletions",
            "source_changes",
            "services_started",
            "model_calls",
        ):
            if type(receipt.get(field)) is not int or receipt[field] != 0:
                raise ValueError("Runtime input publication changed original scope")
        rows = receipt.get("trees")
        if (
            type(rows) is not list
            or len(rows) != 5
            or any(type(row) is not dict for row in rows)
        ):
            raise ValueError("Five explicit original published trees required")
        if (
            any(type(row.get("key")) is not str for row in rows)
            or {row["key"] for row in rows} != TREE_ROLES
        ):
            raise ValueError("Original published Map tree role set differs")
        inventories = []
        for declaration in plan.trees:
            control.checkpoint()
            row = next(row for row in rows if row["key"] == declaration.role)
            if (
                row.get("destination") != declaration.source_root
                or row.get("inventory")
                != {
                    "path": declaration.inventory_path,
                    "sha256": declaration.inventory.sha256,
                }
                or type(row.get("files")) is not int
                or type(row.get("bytes")) is not int
            ):
                raise ValueError("Published inventory/source binding differs")
            raw = object_json(
                read_pinned_bytes(
                    Path(declaration.inventory_path), declaration.inventory, control
                )
            )
            inventory = parse_inventory(raw, declaration)
            if (
                row["files"] != len(inventory.files)
                or row["bytes"] != inventory.size_bytes
            ):
                raise ValueError("Complete published inventory count/bytes differ")
            inventories.append(inventory)
        return tuple(inventories)
