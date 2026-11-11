"""Selected Shopping source facts from the existing discovery and review.

The original CLI native/public bytes are checked once and carried to its supplier
and business entry. Historical facts select a branch, never an owner or claim.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any
from lab_generate_skill.adapters.map_runtime.metadata import object_json
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationInputs,
)
from .shopping_category_navigation import load_category_navigation_inputs

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
        raise ValueError("Bounded canonical Shopping source input required")
    with path.open("rb") as stream:
        raw = stream.read(8 * 1024**2 + 1)
    if not 0 < len(raw) <= 8 * 1024**2:
        raise ValueError("Shopping source input exceeded its bound")
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
        raise OwnershipConflict("Accepted Shopping source bytes changed")
    return raw


def _one(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    selected = [row for row in rows if row[key] == value]
    if len(selected) != 1:
        raise OwnershipConflict("Exactly one original Shopping reference required")
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
        "source_internal_preparation_body_handoff": True,
    }


def _material_matches(
    material: ClosedCategoryNavigationReadMaterial, selected: CategoryNavigationInputs
) -> None:
    declared = material.site.configuration.shopping_category_inputs
    private = selected.private_spec
    if (
        declared is None
        or declared.scope.task != private.task
        or declared.native_contract_sha256 != private.native_contract_ref.sha256
        or material.browser.configuration.spec.scope.task != private.task
    ):
        raise OwnershipConflict(
            "Complete Shopping source changed selected task/native binding"
        )


def prepare_category_source_delta(
    inventory: Path,
    compatibility: Path,
    reference: EvidenceRef,
    public: PublicTask,
    common_evidence: tuple[Path, ...],
    control: OperationControl,
    *,
    complete_material: Path | None = None,
) -> dict[str, Any]:
    found_raw, review_raw = (_raw(p, control) for p in (inventory, compatibility))
    found, review = object_json(found_raw), object_json(review_raw)
    if (
        found.get("group") != "shopping--navigation--1c455a82597b"
        or found.get("member_count") != 18
        or found.get("passed") is not True
        or review.get("passed") is not True
        or review.get("member_count") != 18
        or review.get("inventory") != str(inventory)
        or review.get("inventory_sha256") != hashlib.sha256(found_raw).hexdigest()
    ):
        raise OwnershipConflict("Exact original Shopping18 discovery/review required")
    sid = public.identity.source_task_id
    artifacts = _one(found["rows"], "task_key", "train|shopping|" + sid)[
        "found_artifacts"
    ]
    if len(artifacts) != len(_KINDS) or {x["kind"] for x in artifacts} != _KINDS:
        raise OwnershipConflict("Incomplete Shopping discovery blocks submission")
    native = _one(artifacts, "kind", "native_contract")
    checked = _one(review["rows"], "source_task_id", sid)
    if (
        checked[
            "historical_proof_current_native_fingerprint_and_control_contract_passed"
        ]
        is not True
        or checked["exact_native_contract"] != native
        or checked["historical_admission"]
        != _one(artifacts, "kind", "admission_reference")
    ):
        raise OwnershipConflict("Selected historical Shopping evidence requires review")
    if complete_material is None and any(
        x.get("declared_result_directory_exists") is True for x in artifacts
    ):
        raise OwnershipConflict(
            "Existing source result needs consumer selection; no rebuild fallback"
        )
    raw = _pinned(native, control)
    selected = load_category_navigation_inputs(raw, reference, public)
    complete = None
    if complete_material is not None:
        body = _raw(complete_material, control)
        _material_matches(
            ClosedCategoryNavigationReadMaterial.model_validate_json(body), selected
        )
        complete = _pin(complete_material, body)
    if not common_evidence:
        raise OwnershipConflict("Exact accepted common Shopping receipts required")
    common = []
    for path in common_evidence:
        body = _raw(path, control)
        if object_json(body).get("passed") is not True:
            raise OwnershipConflict("Common Shopping receipt has not passed")
        common.append(_pin(path, body))
    return {
        "schema_version": "shopping-category-source-reuse-delta/1",
        "source_task_id": sid,
        "native_contract": native,
        "native_reference": reference.model_dump(mode="json"),
        "selected": selected.model_dump(mode="json"),
        "found_artifacts": artifacts,
        "inventory": _pin(inventory, found_raw),
        "compatibility": _pin(compatibility, review_raw),
        "common_evidence": common,
        "complete_material": complete,
        "execution": _execution(complete),
        "runtime_or_resume_authority": False,
    }


@dataclass(frozen=True, init=False)
class CategorySourceReuseInputs:
    raw: bytes
    reference: EvidenceRef
    selected: CategoryNavigationInputs
    material: ClosedCategoryNavigationReadMaterial | None
    delta: dict[str, Any]

    def __init__(
        self,
        raw: bytes,
        reference: EvidenceRef,
        public: PublicTask,
        material: ClosedCategoryNavigationReadMaterial | None,
        delta: dict[str, Any],
    ) -> None:
        selected = load_category_navigation_inputs(raw, reference, public)
        if selected != CategoryNavigationInputs.model_validate_json(
            json.dumps(delta["selected"])
        ):
            raise OwnershipConflict(
                "Shopping delta substituted its private/public declaration"
            )
        if material is not None:
            _material_matches(material, selected)
        for name, value in (
            ("raw", raw),
            ("reference", reference),
            ("selected", selected),
            ("material", material),
            ("delta", delta),
        ):
            object.__setattr__(self, name, value)

    def require(
        self, raw: bytes, reference: EvidenceRef, public: PublicTask
    ) -> CategoryNavigationInputs:
        if (
            raw != self.raw
            or reference != self.reference
            or public != self.selected.public_task
            or self.selected.private_spec.native_contract_ref != reference
        ):
            raise OwnershipConflict(
                "Shopping source bodies changed within their original invocation"
            )
        return self.selected


def load_category_source_delta(
    path: Path,
    sha256: str,
    raw: bytes,
    reference: EvidenceRef,
    public: PublicTask,
    control: OperationControl,
) -> CategorySourceReuseInputs:
    body = _raw(path, control)
    if hashlib.sha256(body).hexdigest() != sha256:
        raise OwnershipConflict("Submitted Shopping source delta changed")
    delta = object_json(body)
    if (
        delta["schema_version"] != "shopping-category-source-reuse-delta/1"
        or delta["source_task_id"] != public.identity.source_task_id
        or delta["runtime_or_resume_authority"] is not False
        or delta["execution"] != _execution(delta["complete_material"])
        or not delta["common_evidence"]
    ):
        raise OwnershipConflict("Exact selected Shopping execution branch required")
    artifacts = delta["found_artifacts"]
    if len(artifacts) != len(_KINDS) or {x["kind"] for x in artifacts} != _KINDS:
        raise OwnershipConflict("Shopping delta lost original discovered references")
    native = delta["native_contract"]
    if (
        native != _one(artifacts, "kind", "native_contract")
        or len(raw) != native["size_bytes"]
        or hashlib.sha256(raw).hexdigest() != native["sha256"]
        or reference != EvidenceRef.model_validate(delta["native_reference"])
    ):
        raise OwnershipConflict(
            "Shopping delta changed the original CLI native bytes/reference"
        )
    review = object_json(_pinned(delta["compatibility"], control))
    checked = _one(review["rows"], "source_task_id", public.identity.source_task_id)
    if (
        review["passed"] is not True
        or checked[
            "historical_proof_current_native_fingerprint_and_control_contract_passed"
        ]
        is not True
        or checked["exact_native_contract"] != native
        or checked["historical_admission"]
        != _one(artifacts, "kind", "admission_reference")
    ):
        raise OwnershipConflict(
            "Shopping delta lost exact accepted native/history binding"
        )
    material = (
        None
        if delta["complete_material"] is None
        else ClosedCategoryNavigationReadMaterial.model_validate_json(
            _pinned(delta["complete_material"], control)
        )
    )
    control.checkpoint()
    return CategorySourceReuseInputs(raw, reference, public, material, delta)
