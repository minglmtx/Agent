"""Selected actual task orchestration, keeping each original returned phase."""

from pathlib import Path
from lab_generate_skill.domain.evidence import EvidenceRef
from test_slurm_commands import guard
from typing import Any
import pytest
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.sites.map.tasks.overlay_recovery import (
    OverlaySnapshot,
    OverlayRestored,
)
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from map_qualified_source_native import MapQualifiedSource
from map_task_operations_native import execute
from source_task_hooks import SourceTaskHooks


def run(
    source: MapQualifiedSource,
    hooks: SourceTaskHooks,
    root: Path,
    patch: pytest.MonkeyPatch,
    facts: dict[str, Any],
) -> None:
    n = source.native
    codec = MapTaskStateCodec(n.public.identity)
    request, result = execute(source, "snapshot", None)
    snapshot = codec.snapshot_type.model_validate_json(result.private_result)
    snapshot_ref = n.raw(result.private_result.encode(), snapshot.schema_version)
    facts["snapshot"] = dict(
        request=n.put(request).model_dump(mode="json"),
        result=n.put(result).model_dump(mode="json"),
        snapshot_ref=snapshot_ref.model_dump(mode="json"),
    )
    source.after_snapshot(request, result, snapshot_ref)
    facts["reset_plan_ref"] = source.plan_ref.model_dump(mode="json")
    request, result = execute(source, "prepare", snapshot_ref)
    prepared = n.publish(
        request, result, source.site.site.instance, environment=source.environment
    )
    facts["preparation_records"] = prepared
    run_prepared(
        source,
        hooks,
        root,
        patch,
        facts,
        PreparedPublication.model_validate(prepared["publication"]),
        snapshot_ref,
    )


def run_prepared(
    source: MapQualifiedSource,
    hooks: SourceTaskHooks,
    root: Path,
    patch: pytest.MonkeyPatch,
    facts: dict[str, Any],
    publication: PreparedPublication,
    snapshot_ref: EvidenceRef,
) -> None:
    """Original Actor/evaluation/restore suffix, shared by both producers."""
    n = source.native
    codec = MapTaskStateCodec(n.public.identity)
    snapshot = codec.snapshot_type.model_validate_json(
        n.c.evidence.read(snapshot_ref, control=guard(10))
    )
    observed = source.observe(
        publication,
        root / "browser",
        patch,
        on_session=hooks.session(source),
    )
    facts["prepared_browser"] = observed
    # Callbacks retain Actor/evaluation errors so the original restore can still
    # run after confirmed browser closure. No failed request is repeated here.
    hooks.evaluate(source, facts)
    request, result = execute(source, "restore", snapshot_ref)
    restored = codec.restored_type.model_validate_json(result.private_result)
    assert restored.snapshot == snapshot
    facts["restored"] = dict(
        request=n.put(request).model_dump(mode="json"),
        result=n.put(result).model_dump(mode="json"),
    )
    facts["qualified_source"] = source.after_restore(request, result)
