"""Real byte/file/mount paths with explicitly tiny synthetic image pins.

No SIF is started, no actual source or original-controller permission is granted.
"""

import hashlib
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_runtime.stage import NodeMapInputs
from lab_generate_skill.adapters.map_runtime import stage, tree_copy
from lab_generate_skill.adapters.map_runtime.read_inputs import PublishedMapInputs
from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.map_readonly_binding import bind_map_readonly_inputs
from lab_generate_skill.domain.map_runtime_inputs import IMAGE_PINS, MapRuntimeInputs
from lab_generate_skill.domain.map_services import MapServiceSpec, MapPorts
from lab_generate_skill.sites.map.service_commands import service_commands
from map_runtime_fixtures import runtime_case
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def small_images(root: Path, patch: pytest.MonkeyPatch) -> MapRuntimeInputs:
    for role in IMAGE_PINS:
        raw = ("explicit-unit-image-" + role).encode()
        patch.setitem(IMAGE_PINS, role, (hashlib.sha256(raw).hexdigest(), len(raw)))
    plan = runtime_case(root)
    for image in plan.images:
        path = Path(image.source_path)
        path.parent.mkdir()
        path.write_bytes(("explicit-unit-image-" + image.role).encode())
    return plan


def candidate(source: MapRuntimeInputs, root: Path, name: str) -> MapRuntimeInputs:
    files = source.files.model_copy(
        update={"instance_id": name, "node_root": str(root / name)}
    )
    current = MapRuntimeInputs.model_validate(
        source.model_copy(update={"files": files})
    )
    return bind_map_readonly_inputs(current, source)


def test_two_distinct_instances_use_original_readonly_paths_and_private_writable_trees(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = small_images(node_path, monkeypatch)
    old_wire = source.model_dump_json()
    assert "readonly_inputs" not in old_wire
    NodeMapInputs().stage(source, guard(60))
    inventories = PublishedMapInputs().read(source, guard())
    copies: list[Path] = []

    def copy(source_root: Path, target: Path, *args: Any, **kwargs: Any) -> None:
        copies.append(target)
        copy_pinned_file(source_root, target, *args, **kwargs)

    monkeypatch.setattr(stage, "copy_pinned_file", copy)
    monkeypatch.setattr(tree_copy, "copy_pinned_file", copy)
    plans = [candidate(source, node_path, n) for n in ("candidate-a", "candidate-b")]
    for plan in plans:
        NodeMapInputs().stage(plan, guard(60))
        assert plan.node_tree("routing") == source.node_tree("routing")
        assert all(
            plan.node_image(i.role) == source.node_image(i.role) for i in plan.images
        )
        spec = MapServiceSpec(
            inputs=plan,
            ports=MapPorts(
                web=18001, search=18002, car=18003, bike=18004, foot=18005, tiles=18006
            ),
        )
        commands = service_commands(spec)
        assert source.node_tree("routing") + ":/data:ro" in commands["route_car"]
        assert plan.node_tree("app") + "/postgres:/state/pg" in commands["app_postgres"]
        assert not (Path(plan.files.node_root) / "input/routing").exists()
        assert not list((Path(plan.files.node_root) / "image").iterdir())
        for role in ("app", "search", "tiles", "frontend"):
            assert Path(plan.node_tree(role)).is_dir()
            assert plan.node_tree(role) != source.node_tree(role)
    expected = 2 * sum(len(i.files) for i in inventories if i.role != "routing")
    assert len(copies) == expected and all(
        p.name != "routing" and p.name != "image" for p in copies
    )
    (Path(plans[0].node_tree("app")) / "baseline.json").write_bytes(
        b"candidate private mutation"
    )
    assert (Path(plans[1].node_tree("app")) / "baseline.json").read_bytes() == (
        Path(source.node_tree("app")) / "baseline.json"
    ).read_bytes()
    assert source.model_dump_json() == old_wire
    with pytest.raises(FileExistsError):
        NodeMapInputs().stage(plans[0], guard(60))


@pytest.mark.parametrize(
    "fault", ["image", "routing", "missing", "alias", "writable-image", "late-change"]
)
def test_damaged_retained_assets_never_silently_copy_originals(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    source = small_images(node_path, monkeypatch)
    NodeMapInputs().stage(source, guard(60))
    plan = candidate(source, node_path, "candidate")
    image = Path(source.node_image("web"))
    routing = Path(source.node_tree("routing")) / "stage.json"
    if fault == "image":
        image.chmod(0o600)
        image.write_bytes(b"x" * image.stat().st_size)
        image.chmod(0o444)
    elif fault == "routing":
        routing.write_bytes(b"x" * routing.stat().st_size)
    elif fault == "missing":
        routing.unlink()
    elif fault == "alias":
        image.unlink()
        image.symlink_to(Path(source.images[1].source_path))
    elif fault == "writable-image":
        image.chmod(0o644)
    else:
        original = tree_copy.copy_member

        def changed(*args: Any, **kwargs: Any) -> None:
            original(*args, **kwargs)
            routing.write_bytes(b"x" * routing.stat().st_size)

        monkeypatch.setattr(stage, "copy_member", changed)
    with pytest.raises((EvidenceIntegrityError, FileNotFoundError)):
        NodeMapInputs().stage(plan, guard(60))
    assert Path(plan.files.node_root).exists() == (fault == "late-change")


def test_projection_rejects_nested_or_different_publication_before_io(
    node_path: Path,
) -> None:
    source = runtime_case(node_path)
    plan = candidate(source, node_path, "candidate")
    with pytest.raises(ValueError):
        bind_map_readonly_inputs(plan, source)
    with pytest.raises(ValueError):
        bind_map_readonly_inputs(source, plan)
    current = source.model_copy(update={"publication_job_id": "54321"})
    with pytest.raises(ValueError):
        bind_map_readonly_inputs(current, source)
    assert not Path(source.files.node_root).exists()
