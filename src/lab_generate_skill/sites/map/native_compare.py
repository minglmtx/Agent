"""Pure full-region response/independent DB comparison; no provenance admission."""

import hashlib
from typing import Any, Literal
from .native_bounds import serialized_xml_bounds
from .native_database import database_objects
from .native_xml import parse_native_xml, parse_adapted_xml


def compare_database(
    payload: object,
    original_bounds: object,
    database: object,
    *,
    response_kind: Literal["native_200", "adapted_union"],
) -> dict[str, Any]:
    if response_kind not in ("native_200", "adapted_union"):
        raise ValueError("Explicit native response kind required")
    expected = database_objects(database, original_bounds)
    parsed = (parse_native_xml if response_kind == "native_200" else parse_adapted_xml)(
        payload
    )
    actual = parsed.semantic_objects()
    checks = {
        "serialized_original_bounds": parsed.bounds
        == serialized_xml_bounds(expected.bounds)
    }
    mismatches = {}
    for kind, right in expected.objects.items():
        left = actual[kind]
        checks[kind + "_ids"] = set(left) == set(right)
        checks[kind + "_versions_geometry_tags_members"] = left == right
        mismatches[kind] = dict(
            missing_ids=sorted(set(right) - set(left)),
            extra_ids=sorted(set(left) - set(right)),
            changed_ids=sorted(
                i for i in set(left) & set(right) if left[i] != right[i]
            ),
        )
    assert isinstance(payload, bytes)
    return dict(
        passed=all(checks.values()),
        checks=checks,
        mismatches=mismatches,
        counts={k: len(v) for k, v in actual.items()},
        initial_native_bbox_nodes=len(expected.initial_node_ids),
        api_payload_constructed_expected_reference=False,
        original_full_bbox_preserved=checks["serialized_original_bounds"],
        native_api_cap_changed=False,
        native_single_map_http200_claim=False,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        response_kind=response_kind,
        provenance_verified=False,
    )
