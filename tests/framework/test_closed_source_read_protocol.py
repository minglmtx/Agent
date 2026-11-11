"""Strict whole-graph read wire and original caller boundaries, no execution."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.domain.closed_source_read import (
    ClosedMapReadMaterial,
    ClosedSourceReadCommand,
    ClosedSourcePublicationInput,
)
from lab_generate_skill.domain.evidence_read_scope import EvidenceReadScope
from lab_generate_skill.adapters.plans.closed_source_protocol import (
    encode_command,
    decode_command,
)
from lab_generate_skill.domain.errors import InvalidTransition
from map_closed_source_fixtures import original_closed_source
from source_review_records import ReadOnlyEvidence
from registered_storage_fixtures import request
from test_slurm_commands import guard

E = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-navigation42-production-20261102-v1"
)


def original_material() -> tuple[ClosedMapReadMaterial, Path]:
    data = json.loads(
        (E / "source-qualification-4888671/source-only-qualification.json").read_bytes()
    )
    root = Path(data["evidence_root"])
    declarations = original_closed_source(
        Path(data["facts_path"]), ReadOnlyEvidence(root), guard(30)
    )
    return ClosedMapReadMaterial.model_validate(vars(declarations)), root


def test_original_complete_material_and_context_wire_roundtrip(tmp_path: Path) -> None:
    material, root = original_material()
    original = request(tmp_path, create=True)
    scope = EvidenceReadScope(
        binding=original.binding,
        config=original.config,
        controller=original.controller,
        operation=original.operation,
        revision=0,
    )
    scope = scope.model_copy(
        update={"config": scope.config.model_copy(update={"evidence_root": str(root)})}
    )
    scope = scope.model_copy(
        update={
            "binding": scope.binding.model_copy(
                update={"storage_config_sha256": scope.config.sha256}
            )
        }
    )
    value = ClosedSourceReadCommand(
        scope=scope, workspace_root=str(E.parents[1]), material=material, kind="context"
    )
    raw = encode_command(value)
    assert b'"binding":null' not in raw and decode_command(raw) == value
    assert (
        value.material.site_record.state
        == value.material.browser_record.state
        == "closed"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "unknown"},
        {"kind": "binding"},
        {"binding": None},
        {"publication": None},
        {"kind": "publication"},
        {"workspace_root": ""},
        {"workspace_root": "/tmp/../anvme"},
        {"material": None},
        {"scope": []},
    ],
)
def test_wrong_empty_mixed_kind_and_scope_have_no_effects(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    material, _ = original_material()
    original = request(tmp_path, create=True)
    scope = EvidenceReadScope(
        binding=original.binding,
        config=original.config,
        controller=original.controller,
        operation=original.operation,
        revision=0,
    )
    raw = dict(
        scope=scope, material=material, workspace_root=str(E.parents[1]), kind="context"
    )
    raw.update(change)
    with pytest.raises(ValueError):
        ClosedSourceReadCommand.model_validate(raw)


def test_read_scope_cannot_initialize_or_bypass_quarantine(tmp_path: Path) -> None:
    from managed_store_fixtures import assembled

    current, _ = assembled(tmp_path, Path("/fixed/unlaunched-python"), provision=False)
    with pytest.raises(InvalidTransition):
        with current.read_scope(guard(30)):
            raise AssertionError("uninitialized scope entered")


def proposed_source(
    material: ClosedMapReadMaterial, root: Path
) -> "ClosedSourcePublicationInput":
    from lab_generate_skill.domain.closed_source_read import (
        ClosedSourcePublicationInput,
    )
    from lab_generate_skill.adapters.plans.state_reads import StateReads
    from lab_generate_skill.domain.public_context import PublicContextReceipt
    from lab_generate_skill.domain.baseline import BaselineReceipt
    from lab_generate_skill.domain.reset import ResetReceipt
    from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
    from lab_generate_skill.domain.evidence_identity import evidence_reference
    from lab_generate_skill.domain.evidence import EvidenceMetadata

    reads = StateReads(ReadOnlyEvidence(root))
    control = guard(30)
    context = reads.parse(
        material.context_ref, "public-context-receipt/1", PublicContextReceipt, control
    )
    public = reads.parse(
        context.public_context_ref,
        "public-construction-context/1",
        PublicConstructionContext,
        control,
        visibility="public",
    )
    # Historical8671 public projection has producer native-preparation-engineering.
    # This is a *proposed* current publisher summary over unchanged historical
    # measurements, not a changed historical record or a source permission.
    proposed_ref = evidence_reference(
        public.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema=public.schema_version,
            visibility="public",
            producer="source-qualification-context-v1",
        ),
    )
    return ClosedSourcePublicationInput(
        context=PublicContextReceipt.model_validate(
            context.model_copy(update={"public_context_ref": proposed_ref})
        ),
        public=public,
        baseline=reads.parse(
            context.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
        ),
        reset=reads.parse(context.reset_ref, "reset-receipt/1", ResetReceipt, control),
    )


def proposed_material(
    material: ClosedMapReadMaterial, proposed: ClosedSourcePublicationInput
) -> ClosedMapReadMaterial:
    from lab_generate_skill.domain.evidence_identity import evidence_reference
    from lab_generate_skill.domain.evidence import EvidenceMetadata

    reference = evidence_reference(
        proposed.context.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema=proposed.context.schema_version,
            visibility="private",
            producer="context-records-v1",
        ),
    )
    return ClosedMapReadMaterial.model_validate(
        material.model_copy(update={"context_ref": reference})
    )


def test_proposed_summary_scope_bytes_and_readonly_no_publication_capability() -> None:
    from lab_generate_skill.domain.closed_source_read import (
        ClosedSourcePublicationInput,
    )
    from lab_generate_skill.adapters.storage.readonly_evidence import (
        ReadOnlyEvidence as OriginalCAS,
    )
    from lab_generate_skill.domain.evidence import EvidenceMetadata
    from lab_generate_skill.domain.errors import OwnershipConflict

    material, root = original_material()
    proposed = proposed_source(material, root)
    material = proposed_material(material, proposed)
    store = OriginalCAS(root, max_object_bytes=64 * 1024**2, proposed=proposed)
    assert (
        store.read(material.context_ref, guard(30))
        == proposed.context.model_dump_json().encode()
    )
    with pytest.raises(PermissionError):
        store.put(
            b"foreign",
            EvidenceMetadata(
                media_type="application/json",
                content_schema="public-context-receipt/1",
                visibility="private",
                producer="context-records-v1",
            ),
            guard(30),
        )
    with pytest.raises((ValueError, OwnershipConflict)):
        ClosedSourcePublicationInput.model_validate(
            proposed.model_copy(
                update={
                    "baseline": proposed.baseline.model_copy(
                        update={
                            "scope": proposed.baseline.scope.model_copy(
                                update={"attempt_id": "foreign"}
                            )
                        }
                    )
                }
            )
        )
    bad = proposed.model_copy(
        update={"public": proposed.public.model_copy(update={"context_id": "foreign"})}
    )
    with pytest.raises(OwnershipConflict, match="exact bytes"):
        OriginalCAS(root, max_object_bytes=64 * 1024**2, proposed=bad)
