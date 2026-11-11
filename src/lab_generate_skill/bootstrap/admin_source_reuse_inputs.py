"""Selected Admin source inputs from the original discovery and static review.

The delta chooses the existing complete consumer or current-instance supplement.
It carries immutable bodies into the sole production supplier, never live rights.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any
from lab_generate_skill.adapters.map_runtime.metadata import object_json
from lab_generate_skill.adapters.plans.admin_native_input import decode_admin_native
from lab_generate_skill.domain.claims import SourceClaimKey
from lab_generate_skill.domain.closed_source_read import (
    ClosedAdminNavigationReadMaterial,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    declare_admin_navigation,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_spec import (
    AdminNavigationSpec,
)

_KINDS = {
    "plan",
    "native_contract",
    "/local_contract",
    "/registered_source_preparation",
    "admission_reference",
}
_MISSING = [
    "current_owner_controller_permission_and_claim",
    "current_source_instance_initial_measurements",
    "unique_current_public_initial_observation",
    "current_source_restoration_close_and_context_publication",
]


def _raw(path: Path, control: OperationControl) -> bytes:
    control.checkpoint()
    if (
        not path.is_absolute()
        or path.resolve(strict=True) != path
        or not path.is_file()
        or not 0 < path.stat().st_size <= 8 * 1024**2
    ):
        raise ValueError("Bounded canonical Admin source input required")
    with path.open("rb") as stream:
        raw = stream.read(8 * 1024**2 + 1)
    if len(raw) > 8 * 1024**2:
        raise ValueError("Admin source input exceeded its bound")
    control.checkpoint()
    return raw


def _pin(path: Path, raw: bytes) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _pinned(pin: dict[str, Any], control: OperationControl) -> bytes:
    path = Path(pin["path"])
    raw = _raw(path, control)
    if _pin(path, raw) != {k: pin[k] for k in ("path", "sha256", "size_bytes")}:
        raise OwnershipConflict("Accepted Admin source bytes changed")
    return raw


def _one(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    selected = [row for row in rows if row[key] == value]
    if len(selected) != 1:
        raise OwnershipConflict("Exactly one original Admin reference required")
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


def _declaration(
    raw: bytes, pin: dict[str, Any], source_id: str
) -> tuple[EvidenceRef, AdminNavigationSpec, str]:
    reference = EvidenceRef(
        uri="cas://sha256/" + pin["sha256"],
        sha256=pin["sha256"],
        size_bytes=len(raw),
        media_type="application/json",
        content_schema="admin-native-contract/1",
        visibility="private",
        producer="original-admin-navigation",
    )
    native = decode_admin_native(raw, reference)
    task = TaskIdentity(
        source_task_id=source_id,
        task_id=source_id,
        site="shopping_admin",
        split="train",
        family="page_navigation",
        contract_version=1,
    )
    return (
        reference,
        declare_admin_navigation(native, reference, task, native["goal"]),
        native["goal"],
    )


def prepare_admin_source_delta(
    inventory: Path,
    compatibility: Path,
    source_id: str,
    common_evidence: tuple[Path, ...],
    control: OperationControl,
    *,
    complete_material: Path | None = None,
) -> dict[str, Any]:
    found_raw, review_raw = (_raw(path, control) for path in (inventory, compatibility))
    found, review = object_json(found_raw), object_json(review_raw)
    if (
        found.get("group") != "shopping_admin--navigation--ed0b0c7946c0"
        or found.get("member_count") != 71
        or found.get("passed") is not True
        or review.get("passed") is not True
        or review.get("member_count") != 71
        or review.get("inventory") != str(inventory)
        or review.get("inventory_sha256") != hashlib.sha256(found_raw).hexdigest()
    ):
        raise OwnershipConflict("Exact original Admin71 discovery/review required")
    artifacts = _one(found["rows"], "task_key", "train|shopping_admin|" + source_id)[
        "found_artifacts"
    ]
    if len(artifacts) != len(_KINDS) or {x["kind"] for x in artifacts} != _KINDS:
        raise OwnershipConflict("Incomplete Admin discovery blocks submission")
    native, admission = (
        _one(artifacts, "kind", kind)
        for kind in ("native_contract", "admission_reference")
    )
    checked = _one(review["rows"], "source_task_id", source_id)
    if (
        checked["historical_native_binding_and_reset_evidence_passed"] is not True
        or checked["exact_native_contract"] != native
        or checked["historical_admission"] != admission
    ):
        raise OwnershipConflict("Selected historical Admin evidence requires review")
    if complete_material is None and any(
        x.get("declared_result_directory_exists") is True for x in artifacts
    ):
        raise OwnershipConflict(
            "Existing result metadata requires consumer selection; no rebuild fallback"
        )
    raw = _pinned(native, control)
    reference, private, goal = _declaration(raw, native, source_id)
    complete = None
    if complete_material is not None:
        data = _raw(complete_material, control)
        material = ClosedAdminNavigationReadMaterial.model_validate_json(data)
        _require_material(material, private)
        complete = _pin(complete_material, data)
    if not common_evidence:
        raise OwnershipConflict("Exact accepted common Admin receipts required")
    common = []
    for path in common_evidence:
        data = _raw(path, control)
        if object_json(data).get("passed") is not True:
            raise OwnershipConflict("Common Admin receipt has not passed")
        common.append(_pin(path, data))
    return {
        "schema_version": "admin-source-reuse-delta/1",
        "source_task_id": source_id,
        "native_contract": native,
        "private_spec": private.model_dump(mode="json"),
        "public_goal": goal,
        "found_artifacts": artifacts,
        "inventory": _pin(inventory, found_raw),
        "compatibility": _pin(compatibility, review_raw),
        "common_evidence": common,
        "complete_material": complete,
        "execution": _execution(complete),
        "runtime_or_resume_authority": False,
    }


def _require_material(
    material: ClosedAdminNavigationReadMaterial, private: AdminNavigationSpec
) -> None:
    declared = material.site.configuration.admin_navigation_inputs
    if (
        declared is None
        or (
            declared.scope.task != private.task
            or declared.native_contract_sha256 != private.native_contract_ref.sha256
        )
        or material.browser.configuration.spec.scope.task != private.task
    ):
        raise OwnershipConflict(
            "Complete Admin source changed selected task/native declaration"
        )


@dataclass(frozen=True)
class AdminSourceReuseInputs:
    raw: bytes
    reference: EvidenceRef
    private: AdminNavigationSpec
    goal: str
    material: ClosedAdminNavigationReadMaterial | None
    delta: dict[str, Any]


def load_admin_source_delta(
    path: Path, sha256: str, source_id: str, control: OperationControl
) -> AdminSourceReuseInputs:
    raw = _raw(path, control)
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise OwnershipConflict("Submitted Admin source delta changed")
    delta = object_json(raw)
    if (
        delta["schema_version"] != "admin-source-reuse-delta/1"
        or delta["source_task_id"] != source_id
        or delta["runtime_or_resume_authority"] is not False
        or delta["execution"] != _execution(delta["complete_material"])
        or not delta["common_evidence"]
    ):
        raise OwnershipConflict("Exact selected Admin execution branch required")
    if (
        len(delta["found_artifacts"]) != len(_KINDS)
        or {x["kind"] for x in delta["found_artifacts"]} != _KINDS
    ):
        raise OwnershipConflict("Admin delta lost original discovery references")
    native = _pinned(delta["native_contract"], control)
    review = object_json(_pinned(delta["compatibility"], control))
    checked = _one(review["rows"], "source_task_id", source_id)
    if (
        review["passed"] is not True
        or checked["historical_native_binding_and_reset_evidence_passed"] is not True
        or checked["exact_native_contract"] != delta["native_contract"]
        or checked["exact_native_contract"]
        != _one(delta["found_artifacts"], "kind", "native_contract")
        or checked["historical_admission"]
        != _one(delta["found_artifacts"], "kind", "admission_reference")
    ):
        raise OwnershipConflict(
            "Admin delta lost exact accepted native/history binding"
        )
    reference, private, goal = _declaration(native, delta["native_contract"], source_id)
    if (
        private != AdminNavigationSpec.model_validate(delta["private_spec"])
        or goal != delta["public_goal"]
    ):
        raise OwnershipConflict(
            "Admin delta substituted its declaration or public goal"
        )
    material = (
        None
        if delta["complete_material"] is None
        else ClosedAdminNavigationReadMaterial.model_validate_json(
            _pinned(delta["complete_material"], control)
        )
    )
    if material is not None:
        _require_material(material, private)
    control.checkpoint()
    return AdminSourceReuseInputs(native, reference, private, goal, material, delta)


def require_admin_source_unclaimed(
    root: Path, source_id: str, control: OperationControl
) -> None:
    """Refusal only; the original atomic claim remains the real permission gate."""
    control.checkpoint()
    if root.resolve(strict=True) != root or not root.is_dir():
        raise OwnershipConflict("Original canonical Admin claim scope required")
    key = SourceClaimKey(
        scope_id="admin-navigation71-engineering-once", source_task_id=source_id
    )
    if any(root.glob(key.filename + "*")):
        raise OwnershipConflict("Consumed or uncertain Admin claim cannot be replayed")
    control.checkpoint()
