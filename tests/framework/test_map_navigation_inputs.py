"""Exact byte binding, strict private declarations, derived identity and public separation."""

import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.bootstrap.map_navigation import load_navigation_inputs
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.map.tasks.navigation_spec import (
    NavigationInputs,
    NavigationSourceBinding,
)
from lab_generate_skill.sites.map.navigation_rules import original_completion
from map_navigation_fixtures import (
    SOURCES,
    ORIGIN,
    navigation_case,
    changed_case,
    reference,
)


@pytest.mark.parametrize("source", SOURCES)
def test_original_native_bytes_all_route_fields_and_source_lineage_are_preserved(
    source: str, tmp_path: Path
) -> None:
    c = navigation_case(source)
    result = c.load()
    spec = result.private_spec
    assert (
        result
        == c.load()
        == NavigationInputs.model_validate_json(result.model_dump_json())
    )
    assert spec.native_contract_ref.sha256 == c.binding.native_contract.sha256
    assert spec.native_contract_ref.sha256 != c.binding.original_contract_sha256
    assert (
        spec.native_contract_ref.size_bytes == len(c.raw)
        and spec.admission == "unverified"
    )
    assert original_completion(spec.completion) == c.native["completion"]
    assert spec.binding.registration_status == (
        "success" if source == SOURCES[0] else "failure"
    )
    if source == SOURCES[0]:
        assert (
            spec.goal_revision is not None
            and not spec.goal_revision.original_benchmark_equivalence
        )
        assert (
            spec.task.task_id
            != spec.binding.runtime_task_id
            == spec.task.source_task_id
        )
    else:
        assert (
            spec.goal_revision is None
            and spec.task.task_id == spec.binding.runtime_task_id
        )
        assert spec.completion.map_route is not None
        assert spec.completion.map_route.alternatives[0].backend_json == json.dumps(
            c.native["completion"]["map_route"]["alternatives"][0]["backend"],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        assert len(c.raw) == 345541
    public = result.public_task.model_dump_json()
    assert all(
        name not in public
        for name in (
            "native_contract_ref",
            "backend_json",
            "alternatives",
            "admission_result",
            "retained_control_review",
        )
    )
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize(
    "field,value",
    [
        ("source_task_id", "foreign"),
        ("task_id", "foreign"),
        ("goal", "other goal"),
        ("heldout_quarantine", True),
        ("split", "test"),
        ("api_calls", False),
        ("api_calls", 1),
        ("start_path", "/other"),
        ("source_trace_ids", []),
        ("recorded_start_paths", []),
        ("completion", {}),
        ("completion", None),
        ("completion", []),
        ("extra", "not ignored"),
        ("goal_revision", None),
    ],
)
def test_illegal_original_contract_refused_without_relaxing_reference_binding(
    source: str, field: str, value: Any
) -> None:
    c = navigation_case(source)
    c.native[field] = value
    with pytest.raises(EvidenceIntegrityError):
        changed_case(c, c.native).load()


@pytest.mark.parametrize(
    "raw",
    [None, "{}", 1, [], b"", b"{}", b"[1]", b" " * (1024 * 1024 + 1)],
    ids=[
        "none",
        "text",
        "integer",
        "list",
        "empty",
        "empty-object",
        "array",
        "oversize",
    ],
)
def test_empty_wrong_type_or_oversize_bytes_are_refused(raw: Any) -> None:
    c = navigation_case()
    with pytest.raises(EvidenceIntegrityError):
        load_navigation_inputs(raw, reference(c.raw), c.public, binding=c.binding)


@pytest.mark.parametrize("fault", ["bytes", "size", "digest", "visibility", "schema"])
def test_exact_original_reference_is_required(fault: str) -> None:
    c = navigation_case()
    ref = reference(c.raw)
    raw = c.raw
    if fault == "bytes":
        raw += b" "
    elif fault == "size":
        ref = ref.model_copy(update={"size_bytes": ref.size_bytes + 1})
    elif fault == "digest":
        ref = ref.model_copy(update={"sha256": "0" * 64})
    elif fault == "visibility":
        ref = ref.model_copy(update={"visibility": "public"})
    else:
        ref = ref.model_copy(update={"content_schema": "other/1"})
    with pytest.raises(EvidenceIntegrityError):
        load_navigation_inputs(raw, ref, c.public, binding=c.binding)


@pytest.mark.parametrize(
    "field,value",
    [
        ("active_task_id", "unbound"),
        ("runtime_task_id", "other-runtime"),
        ("source_task_id", "other-source"),
        ("public_goal", "other goal"),
        ("protocol", "map_data"),
        ("evaluator_version", "other-version"),
        ("extra", "not ignored"),
    ],
)
def test_unknown_or_mismatched_source_binding_never_grants_input(
    field: str, value: Any
) -> None:
    c = navigation_case()
    data = c.binding.model_dump(mode="json")
    data[field] = value
    with pytest.raises((ValidationError, EvidenceIntegrityError)):
        binding = NavigationSourceBinding.model_validate_json(json.dumps(data))
        load_navigation_inputs(c.raw, reference(c.raw), c.public, binding=binding)


@pytest.mark.parametrize(
    "fault", ["goal", "identity", "heldout", "remote", "port", "start", "actions"]
)
def test_public_template_must_keep_selected_scope_and_allocated_start(
    fault: str,
) -> None:
    c = navigation_case()
    data = c.public.model_dump(mode="json")
    if fault == "goal":
        data["goal"] = "Read all external community sites"
    elif fault == "identity":
        data["identity"]["task_id"] = c.binding.runtime_task_id
    elif fault == "heldout":
        data["identity"]["split"] = "dev"
    elif fault == "remote":
        data["start_url"] = "http://remote:12001" + c.native["start_path"]
    elif fault == "port":
        data["start_url"] = "http://127.0.0.1:1" + c.native["start_path"]
    elif fault == "start":
        data["start_url"] = ORIGIN + "/communities"
    else:
        data["allowed_actions"] = ["click"]
    with pytest.raises(EvidenceIntegrityError):
        load_navigation_inputs(
            c.raw,
            reference(c.raw),
            PublicTask.model_validate_json(json.dumps(data)),
            binding=c.binding,
        )


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "null",
        "mode",
        "nan",
        "partial-backend",
        "bad-pattern",
        "unknown-completion",
    ],
)
def test_full_route_or_navigation_declaration_cannot_be_truncated_or_reinterpreted(
    fault: str,
) -> None:
    c = navigation_case(SOURCES[1])
    route = c.native["completion"]["map_route"]
    if fault == "empty":
        route["alternatives"] = []
    elif fault == "null":
        c.native["completion"]["map_route"] = None
    elif fault == "mode":
        route["alternatives"][0]["profile"] = "foot"
    elif fault == "nan":
        route["pair"][0][0] = "NaN"
    elif fault == "partial-backend":
        route["alternatives"][0]["backend"] = {"distance": 1}
    elif fault == "bad-pattern":
        c.native["completion"]["heading_regex"] = "["
    else:
        c.native["completion"]["map_editor"] = {"kind": "unexpected"}
    with pytest.raises(EvidenceIntegrityError):
        changed_case(c, c.native).load()
