"""Original selected reference region, never historical admission or expected objects."""

from decimal import Decimal
import hashlib
import json
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from ..native_bounds import Bounds, request_bounds
from ..terminal_files import private_bytes
from ..state_rules import object_json
from .overlay_spec import SOURCE, GOAL, START

PROOF_SHA = "95ca64fc4c3d113d183b3ec01fe65511f2c556633b8c35e4aa0ea8f6208209ea"
CONTRACT_SHA = "50356bbd0811eaac447f9bbef29a348a552dc38c2478a1cbec13464f1719cb2d"


def original_reference_bounds(
    store: EvidenceReader, ref: EvidenceRef, control: OperationControl
) -> Bounds:
    if ref.sha256 != PROOF_SHA:
        raise EvidenceIntegrityError(
            "Exact selected original Map reference proof required"
        )
    value = object_json(private_bytes(store, ref, "map-native-layer-proof/1", control))
    # Exact historical bytes are pinned above. Read this source's two matching
    # regions; do not import its seven-task control gate or reuse its DB objects.
    regions = []
    for cycle in value["native_cycles"]:
        row = next(r for r in cycle["sources"] if r["source_task_id"] == SOURCE)
        reference = row["reference"]
        if (
            reference["original_goal"],
            reference["original_first_start"],
            reference["kind"],
            reference["native_cap_remains"],
        ) != (GOAL, START, "complete_original_native_mapdata", 50000):
            raise EvidenceIntegrityError(
                "Original selected Map reference meaning changed"
            )
        if (
            hashlib.sha256(
                json.dumps(
                    reference, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest()
            != row["reference_signature"]
        ):
            raise EvidenceIntegrityError("Original Map reference signature changed")
        regions.append(request_bounds(reference["bbox"]))
    if len(regions) != 2 or regions[0] != regions[1]:
        raise EvidenceIntegrityError("Original Map reference regions disagree")
    return regions[0]


def full_original_bbox_retained(current: object, original: object) -> bool:
    try:
        w, s, e, n = map(Decimal, request_bounds(current))
        a, b, c, d = map(Decimal, request_bounds(original))
        return w <= a and s <= b and e >= c and n >= d
    except (ValueError, TypeError):
        return False
