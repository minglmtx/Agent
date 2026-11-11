"""Map's selected input delta over existing group discovery and source consumer.

No producer, installation, historical validator or permission is run here. The
bounded selected delta preserves partial evidence and requires an explicit route;
the existing owner/claim/instance gates remain at the actual production entry.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any
from lab_generate_skill.actor.instructions import ACTIONS
from lab_generate_skill.adapters.map_runtime.metadata import object_json
from lab_generate_skill.bootstrap.map_navigation_source import (
    MapNavigationSourceSelection,
)
from lab_generate_skill.domain.closed_source_read import ClosedMapReadMaterial
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.claims import SourceClaimKey
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSourceBinding

_MISSING = (
    "current_owner_controller_permission_and_claim",
    "current_source_instance_initial_measurements",
    "unique_current_public_initial_observation",
    "current_source_restoration_close_and_context_publication",
)
_KINDS = {
    "plan",
    "native_contract",
    "/local_contract",
    "/registered_source_preparation",
    "admission_reference",
}


def _raw(path: Path, control: OperationControl) -> bytes:
    control.checkpoint()
    if (
        not path.is_absolute()
        or path.resolve(strict=True) != path
        or not path.is_file()
        or not 0 < path.stat().st_size <= 8 * 1024**2
    ):
        raise ValueError("Bounded canonical source input required")
    with path.open("rb") as stream:
        raw = stream.read(8 * 1024**2 + 1)
    if len(raw) > 8 * 1024**2:
        raise ValueError("Source input exceeded its bound")
    control.checkpoint()
    return raw


def _pin(path: Path, raw: bytes) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _pinned(pin: dict[str, Any], control: OperationControl) -> bytes:
    raw = _raw(Path(pin["path"]), control)
    if _pin(Path(pin["path"]), raw) != {
        key: pin[key] for key in ("path", "sha256", "size_bytes")
    }:
        raise OwnershipConflict("Source input changed its exact accepted bytes")
    return raw


def _one(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    selected = [row for row in rows if row[key] == value]
    if len(selected) != 1:
        raise OwnershipConflict(
            "Source discovery requires exactly one selected reference"
        )
    return selected[0]


def _execution(complete: object) -> dict[str, Any]:
    return {
        "mode": (
            "consume_complete"
            if complete is not None
            else "supplement_current_instance"
        ),
        "reuse": [
            "native_contract_and_preparation_binding",
            "historical_admission_compatibility",
            "accepted_common_software_installation_assets",
        ],
        "supplement": [] if complete is not None else list(_MISSING),
        "source_producer_calls": 0 if complete is not None else 1,
        "historical_validator_calls": 0,
        "common_check_or_install_calls": 0,
    }


def prepare_map_source_delta(
    group_plan: Path,
    inventory: Path,
    compatibility: Path,
    source_id: str,
    common_evidence: tuple[Path, ...],
    control: OperationControl,
    *,
    complete_material: Path | None = None,
) -> dict[str, Any]:
    """Select existing receipts; missing discovery is an error, never empty history."""
    group_raw, found_raw, review_raw = (
        _raw(path, control) for path in (group_plan, inventory, compatibility)
    )
    group, found, review = (
        object_json(raw) for raw in (group_raw, found_raw, review_raw)
    )
    if (
        group["effective_batch_id"] != "map--navigation--c33aa10c2123"
        or found["passed"] is not True
        or review["passed"] is not True
    ):
        raise OwnershipConflict(
            "Original accepted Map discovery and compatibility required"
        )
    if (
        review["inventory"] != str(inventory)
        or review["inventory_sha256"] != hashlib.sha256(found_raw).hexdigest()
    ):
        raise OwnershipConflict("Historical compatibility changed discovery input")
    member = _one(group["members"], "source_task_id", source_id)
    task_key = "train|map|" + source_id
    artifacts = _one(found["rows"], "task_key", task_key)["found_artifacts"]
    checked = _one(review["rows"], "source_task_id", source_id)
    if len(artifacts) != len(_KINDS) or {item["kind"] for item in artifacts} != _KINDS:
        raise OwnershipConflict(
            "Incomplete discovery must be resolved before submission"
        )
    binding = NavigationSourceBinding.model_validate(member["source_binding"])
    native, admission = (
        _one(artifacts, "kind", kind)
        for kind in ("native_contract", "admission_reference")
    )
    if (
        checked[
            "historical_proof_current_native_fingerprint_and_control_contract_passed"
        ]
        is not True
        or checked["exact_native_contract"] != native
        or checked["historical_admission"] != admission
        or native["sha256"] != member["contract_pin"]["expected_sha256"]
        or native["sha256"] != binding.native_contract.sha256
        or native["path"] != binding.native_contract.path
        or admission["sha256"] != binding.admission.sha256
    ):
        raise OwnershipConflict(
            "Selected historical compatibility requires affected-input review"
        )
    if complete_material is None and any(
        item.get("declared_result_directory_exists") is True for item in artifacts
    ):
        raise OwnershipConflict(
            "Existing result metadata needs consumer selection; no fallback rebuild"
        )
    complete = None
    if complete_material is not None:
        raw = _raw(complete_material, control)
        ClosedMapReadMaterial.model_validate_json(raw)
        complete = _pin(complete_material, raw)
    if not common_evidence:
        raise OwnershipConflict(
            "Accepted common receipts must be explicitly referenced"
        )
    common = []
    for path in common_evidence:
        raw = _raw(path, control)
        if object_json(raw).get("passed") is not True:
            raise OwnershipConflict("Common evidence is not an accepted receipt")
        common.append(_pin(path, raw))
    return {
        "schema_version": "map-source-reuse-delta/1",
        "source_task_id": source_id,
        "source_binding": binding.model_dump(mode="json"),
        "native_contract": native,
        "found_artifacts": artifacts,
        "group_plan": _pin(group_plan, group_raw),
        "inventory": _pin(inventory, found_raw),
        "compatibility": _pin(compatibility, review_raw),
        "common_evidence": common,
        "complete_material": complete,
        "execution": _execution(complete),
        "runtime_or_resume_authority": False,
    }


@dataclass(frozen=True)
class MapSourceReuseInputs:
    selection: MapNavigationSourceSelection
    material: ClosedMapReadMaterial | None
    delta: dict[str, Any]


def load_map_source_delta(
    path: Path, sha256: str, source_id: str, control: OperationControl
) -> MapSourceReuseInputs:
    raw = _raw(path, control)
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise OwnershipConflict("Submitted source delta changed")
    delta = object_json(raw)
    if (
        delta["schema_version"] != "map-source-reuse-delta/1"
        or delta["source_task_id"] != source_id
        or delta["runtime_or_resume_authority"] is not False
    ):
        raise OwnershipConflict("Exact selected source delta required")
    if delta["execution"] != _execution(delta["complete_material"]):
        raise OwnershipConflict(
            "Source delta does not select the exact execution branch"
        )
    if not delta["common_evidence"]:
        raise OwnershipConflict("Source delta omitted accepted common evidence")
    # One selected native body and its existing compatibility receipt. Do not
    # reload historical admissions, reconstruct source plans or repeat controls.
    native = _pinned(delta["native_contract"], control)
    review = object_json(_pinned(delta["compatibility"], control))
    checked = _one(review["rows"], "source_task_id", source_id)
    binding = NavigationSourceBinding.model_validate(delta["source_binding"])
    if (
        review["passed"] is not True
        or checked[
            "historical_proof_current_native_fingerprint_and_control_contract_passed"
        ]
        is not True
        or checked["exact_native_contract"] != delta["native_contract"]
        or checked["historical_admission"]
        != _one(delta["found_artifacts"], "kind", "admission_reference")
        or (binding.native_contract.path, binding.native_contract.sha256)
        != (delta["native_contract"]["path"], delta["native_contract"]["sha256"])
        or binding.admission.sha256 != checked["historical_admission"]["sha256"]
    ):
        raise OwnershipConflict("Delta lost exact accepted historical/native binding")
    original = object_json(native)
    public = PublicTask(
        identity=TaskIdentity(
            site="map",
            family="navigation_page_identity",
            contract_version=1,
            split="train",
            task_id=binding.active_task_id,
            source_task_id=source_id,
        ),
        goal=binding.public_goal,
        start_url="http://127.0.0.1:1024" + original["start_path"],
        allowed_actions=tuple(ACTIONS),
    )
    selection = MapNavigationSourceSelection(native, binding, public)
    selection.load(selection.reference(), public)
    material = (
        None
        if delta["complete_material"] is None
        else ClosedMapReadMaterial.model_validate_json(
            _pinned(delta["complete_material"], control)
        )
    )
    control.checkpoint()
    return MapSourceReuseInputs(selection, material, delta)


def require_map_source_unclaimed(
    root: Path, source_id: str, control: OperationControl
) -> None:
    """Fresh refusal only; the original atomic claim remains authoritative."""
    control.checkpoint()
    if root.resolve(strict=True) != root or not root.is_dir():
        raise OwnershipConflict("Original canonical claim scope required")
    key = SourceClaimKey(
        scope_id="map-navigation42-engineering-once", source_task_id=source_id
    )
    if any(root.glob(key.filename + "*")):
        raise OwnershipConflict(
            "Original consumed or uncertain claim cannot be replayed"
        )
    control.checkpoint()
