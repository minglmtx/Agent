"""Existing category sources through the real entry; native effects are forbidden."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.bootstrap.shopping_category_source_qualification import (
    qualify_category_navigation_source,
)
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    OperationStopped,
    OwnershipConflict,
)
from shopping_category_source_fixtures import source_unit_case
from shopping_category_owned_reads import CategoryUnitRead
from site_instance_fixtures import node_path as node_path
from test_shopping_category_navigation_input import originals as originals, reference
import lab_generate_skill.bootstrap.shopping_category_source_qualification as module


def retained_case(
    root: Path, node: Path, patch: pytest.MonkeyPatch, original: Any
) -> Any:
    x = source_unit_case(root, node, patch, original, "none")
    qualified = x.run()
    reads = CategoryUnitRead(x, root / "evidence", x.site.op)
    effects: list[str] = []

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        effects.append("unexpected source effect")
        raise AssertionError("Existing source must not acquire, publish or rebuild")

    patch.setattr(module, "RetainedSiteResource", forbidden)
    patch.setattr(module, "SourceQualificationNativeAuthority", forbidden)
    patch.setattr(x.site.evidence, "put", forbidden)
    parameters = dict(
        owner=x.owner,
        spec=x.site.spec,
        acquisition=x.site.op,
        raw=original[0],
        native_ref=reference(original[0]),
        public=qualified.inputs.context.task,
        assets=x.assets,
        journal=x.site.journal,
        controls=x.site.controls,
        clock=x.site.clock,
        prefix="retained-category-unit",
        metadata_seconds=120,
        source_reads=reads,
        retained_source=qualified.material,
    )
    return SimpleNamespace(
        source=x,
        qualified=qualified,
        reads=reads,
        effects=effects,
        parameters=parameters,
    )


def test_existing_category_entry_reads_once_and_returns_original_complete_inputs(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, originals: Any
) -> None:
    c = retained_case(tmp_path, node_path, monkeypatch, originals[0])
    result = qualify_category_navigation_source(**c.parameters)
    assert result.material == c.qualified.material
    assert result.receipt == c.qualified.receipt
    assert result.inputs == c.qualified.inputs
    assert c.reads.calls == 1 and not c.effects
    assert c.source.owner._sealed


@pytest.mark.parametrize(
    "fault", ["task", "version", "private", "installation", "missing", "public"]
)
def test_changed_or_missing_category_source_refuses_without_rebuild(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    c = retained_case(tmp_path, node_path, monkeypatch, originals[0])
    parameters = c.parameters
    material = parameters["retained_source"]
    expected: type[Exception] = OwnershipConflict
    if fault == "task":
        parameters.update(
            raw=originals[1][0],
            native_ref=reference(originals[1][0]),
            public=originals[1][2],
        )
    elif fault in ("version", "private"):
        cfg = material.site.configuration
        inputs = cfg.shopping_category_inputs
        assert inputs is not None
        update = (
            {
                "schema_version": "site-worker-configuration/6",
                "shopping_category_inputs": None,
            }
            if fault == "version"
            else {
                "shopping_category_inputs": inputs.model_copy(
                    update={"private_input_sha256": "0" * 64}
                )
            }
        )
        parameters["retained_source"] = material.model_copy(
            update={
                "site": material.site.model_copy(
                    update={"configuration": cfg.model_copy(update=update)}
                )
            }
        )
    elif fault == "installation":
        spec = parameters["spec"]
        cfg = spec.configuration
        parameters["spec"] = spec.model_copy(
            update={
                "configuration": cfg.model_copy(
                    update={
                        "installation": cfg.installation.model_copy(
                            update={"python_executable": "/tmp/unverified-python"}
                        )
                    }
                )
            }
        )
    elif fault == "missing":
        parameters["retained_source"] = material.model_copy(
            update={
                "context_ref": material.context_ref.model_copy(
                    update={"sha256": "0" * 64, "uri": "cas://sha256/" + "0" * 64}
                )
            }
        )
        expected = EvidenceNotFound
    elif fault == "public":
        parameters["public"] = parameters["public"].model_copy(
            update={"allowed_actions": ("send_msg_to_user",)}
        )
    with pytest.raises(expected):
        qualify_category_navigation_source(**parameters)
    assert not c.effects and c.source.owner._sealed


@pytest.mark.parametrize(
    "fault", ["before-revoke", "after-revoke", "before-cancel", "after-cancel"]
)
def test_category_consumption_rechecks_current_rights_and_retains_stop(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    c = retained_case(tmp_path, node_path, monkeypatch, originals[0])
    stopped = [fault.startswith("before")]
    original_caller = c.source.owner.require_caller

    def current(operation: Any, control: Any) -> None:
        original_caller(operation, control)
        if stopped[0]:
            if fault.endswith("cancel"):
                raise OperationStopped("CANCELLED", operation.operation_id)
            raise PermissionError("Original category consumption permission revoked")

    original_read = c.reads.read

    def read(*args: Any, **kwargs: Any) -> Any:
        value = original_read(*args, **kwargs)
        stopped[0] = True
        return value

    monkeypatch.setattr(c.source.owner, "require_caller", current)
    monkeypatch.setattr(c.reads, "read", read)
    expected = OperationStopped if fault.endswith("cancel") else PermissionError
    with pytest.raises(expected):
        qualify_category_navigation_source(**c.parameters)
    assert c.reads.calls == (0 if fault.startswith("before") else 1)
    assert not c.effects and c.source.owner._sealed
