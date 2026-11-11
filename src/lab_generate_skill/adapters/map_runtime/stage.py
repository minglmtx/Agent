"""Selected Map staging, inside the original acquisition/supervision boundary.

This is a worker leaf, not a new public permission or standalone execution entry.
The current fixed site worker does not dispatch Map until explicitly wired.
"""

from pathlib import Path
from functools import partial
from collections.abc import Iterator
from lab_generate_skill.adapters.operation_progress import operation_stage
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeInputs
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.files import NodeSiteFiles
from lab_generate_skill.adapters.releases.artifact_copy import (
    copy_pinned_file,
    sync_directory,
    FileIdentity,
)
from .read_inputs import PublishedMapInputs
from .tree_copy import check_tree, prepare_clone, copy_member, finish_clone
from .copy_queue import CopyWork, copy_files
from .readonly_inputs import verify_readonly_inputs, recheck_readonly_inputs


class NodeMapInputs:
    def stage(self, plan: MapRuntimeInputs, control: OperationControl) -> None:
        plan = MapRuntimeInputs.model_validate(plan)
        inventories = PublishedMapInputs().read(plan, control)
        # Complete declarations and tree shapes are checked before image/data
        # copying. Full content hashes are verified by the existing file copier.
        with operation_stage("map.stage.preflight"):
            checked = tuple(
                check_tree(declaration, inventory, control)
                for declaration, inventory in zip(plan.trees, inventories, strict=True)
            )
        retained: dict[Path, FileIdentity] = {}
        if plan.readonly_inputs is not None:
            with operation_stage("map.stage.readonly-inputs"):
                retained = verify_readonly_inputs(
                    plan, next(x for x in inventories if x.role == "routing"), control
                )
            NodeSiteFiles().prepare(plan.files, control)
        else:
            with operation_stage("map.stage.web-image"):
                NodeSiteFiles().stage(plan.files, control)
            for image in plan.images:
                if image.role != "web":
                    copy_pinned_file(
                        Path(image.source_path).parent,
                        Path(plan.files.node_root) / "image",
                        image.file,
                        control,
                    )
        sync_directory(Path(plan.files.node_root) / "image")
        inputs = Path(plan.files.node_root) / "input"
        inputs.mkdir(mode=0o700)
        with operation_stage("map.stage.tree-layout"):
            clones = tuple(
                prepare_clone(
                    declaration,
                    inventory,
                    Path(plan.node_tree(declaration.role)),
                    control,
                    checked=proof,
                )
                for declaration, inventory, proof in zip(
                    plan.trees, inventories, checked, strict=True
                )
                if not (
                    plan.readonly_inputs is not None and declaration.role == "routing"
                )
            )

        def work() -> Iterator[CopyWork]:
            for clone in clones:
                for member in clone.checked.inventory.files:
                    yield CopyWork(
                        partial(copy_member, clone, member),
                        member.file.size_bytes,
                    )

        with operation_stage("map.stage.file-copy"):
            copied = copy_files(work(), control)
        with operation_stage("map.stage.final-check"):
            for clone in clones:
                finish_clone(clone, control)
            recheck_readonly_inputs(retained, control)
        # Counts describe this completed data-copy scope, not image/directory
        # syncs or total device traffic. Diagnostics never mask original work.
        import sys

        try:
            if plan.readonly_inputs is not None:
                routing = next(x for x in inventories if x.role == "routing")
                sys.stderr.write(
                    f"MAP_STAGE_READONLY images={len(plan.images)} routing_files={len(routing.files)} routing_bytes={routing.size_bytes} image_copies=0 routing_copies=0\n"
                )
            sys.stderr.write(
                f"MAP_STAGE_IO files={copied.files} declared_bytes={copied.size_bytes} peak_in_flight={copied.peak_in_flight} data_fsyncs={copied.files} tree_inspections={2 * len(clones)}\n"
            )
            sys.stderr.flush()
        except Exception:
            pass
        sync_directory(inputs)
        sync_directory(Path(plan.files.node_root))
        control.checkpoint()
