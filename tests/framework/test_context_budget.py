"""Finite role budget and binding tests; no semantic/quality or request admission claim."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any
import json
import pytest
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.adapters.plans.context_projection import (
    MAX_CONTEXT_METADATA,
    decode_context_budget,
    decode_context_selection,
    decode_context_decision,
)
from lab_generate_skill.domain.context_budget import (
    ContextBudgetProfile,
    TokenMeasurement,
)
from lab_generate_skill.domain.context_projection import (
    ContextSelection,
    ContextProjectionPolicy,
)
from lab_generate_skill.policies.context_budget import select_candidate
from context_budget_fixtures import profile, selection, ref


@pytest.mark.parametrize("role", ["actor", "teacher"])
@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
def test_short_complete_requests_take_same_noop_role_path(
    role: Any, site: Site
) -> None:
    request = selection((80, 60), role=role, site=site)
    before = request.model_dump_json()
    result = select_candidate(request)
    assert result.accepted and result.selected_candidate_id == "format-0"
    assert result.reason_code == "below_soft_identity"
    assert result.source == request.candidates[0].source
    assert result.assessments[0].within_soft and result.assessments[0].within_hard
    assert request.model_dump_json() == before
    assert decode_context_decision(result.model_dump_json().encode()) == result


@pytest.mark.parametrize(
    "tokens,accepted,soft",
    [
        (79, True, True),
        (80, True, True),
        (81, True, False),
        (99, True, False),
        (100, True, False),
        (101, False, False),
    ],
)
def test_soft_and_hard_boundaries_use_whole_request(
    tokens: int, accepted: bool, soft: bool
) -> None:
    result = select_candidate(selection((tokens,)))
    assert result.accepted is accepted
    assert result.assessments[0].within_soft is soft
    assert result.assessments[0].within_hard is accepted
    assert (
        result.selected_input_ref is None
        if not accepted
        else result.selected_input_ref is not None
    )
    if not accepted:
        assert result.reason_code == "input_budget_exceeded"


def test_real_Map_counts_need_not_reach_soft_target_or_change_hard_gate() -> None:
    limits = profile(
        context_window=32768, output_reserve=4096, input_limit=28672, soft_target=24576
    )
    request = selection(
        (37839, 26790),
        kinds=("identity", "structural_ax"),
        structural=True,
        configuration=limits,
    )
    result = select_candidate(request)
    assert result.accepted and result.selected_candidate_id == "format-1"
    assert not result.assessments[1].within_soft and result.assessments[1].within_hard
    assert result.reason_code == "shorter_verified_candidate"


@pytest.mark.parametrize(
    "values,expected",
    [
        ((90, 90), "format-0"),
        ((90, 95), "format-0"),
        ((90, 89), "format-1"),
        ((110, 100), "format-1"),
        ((110, 101), None),
        ((90, 70, 70), "format-1"),
    ],
)
def test_only_shorter_verified_candidates_selected_and_equal_ties_use_frozen_order(
    values: tuple[int, ...], expected: str | None
) -> None:
    result = select_candidate(selection(values))
    assert result.selected_candidate_id == expected
    assert result.accepted is (expected is not None)


@pytest.mark.parametrize("status", ["fail", "unknown"])
def test_invalid_transformed_candidate_retains_valid_identity_only_when_declared(
    status: str,
) -> None:
    request = selection((90, 60))
    bad = request.candidates[1].model_copy(
        update={
            "checks": tuple(
                c.model_copy(update={"status": status})
                for c in request.candidates[1].checks
            )
        }
    )
    request = request.model_copy(update={"candidates": (request.candidates[0], bad)})
    assert select_candidate(request).reason_code == "identity_fallback"
    denied = request.model_copy(
        update={
            "policy": request.policy.model_copy(
                update={"allow_identity_fallback": False}
            )
        }
    )
    # Changed policy invalidates every candidate's policy binding before choice.
    with pytest.raises(ValueError):
        select_candidate(denied)
    no_fallback = selection((90, 90), allow_fallback=False)
    assert select_candidate(no_fallback).reason_code == "no_permitted_candidate"
    rejected = selection((90, 60), check_status=status)
    result = select_candidate(rejected)
    assert not result.accepted and result.reason_code == "integrity_rejected"


def test_forced_validated_format_is_explicit_and_still_has_hard_limit() -> None:
    assert (
        select_candidate(
            selection((60, 70), forced="exact_body_sharing")
        ).selected_candidate_id
        == "format-1"
    )
    rejected = select_candidate(selection((60, 101), forced="exact_body_sharing"))
    assert not rejected.accepted and rejected.reason_code == "input_budget_exceeded"


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"provider_input_limit": 90}, 90),
        ({"context_window": 115, "uncounted_overhead": 5}, 90),
        ({"input_limit": 85}, 85),
    ],
)
def test_input_provider_template_output_and_overhead_all_limit_profile(
    changes: dict[str, Any], expected: int
) -> None:
    p = profile(**changes)
    assert p.hard_limit == expected
    assert select_candidate(selection((expected,), configuration=p)).accepted
    assert not select_candidate(selection((expected + 1,), configuration=p)).accepted


@pytest.mark.parametrize(
    "field",
    [
        "context_window",
        "output_reserve",
        "input_limit",
        "provider_input_limit",
        "soft_target",
    ],
)
@pytest.mark.parametrize(
    "value", [True, False, 0, -1, 1.5, float("nan"), float("inf"), "100", None]
)
def test_budget_limits_reject_boolean_noninteger_nonfinite_missing_space(
    field: str, value: Any
) -> None:
    if field == "provider_input_limit" and value is None:
        assert profile(provider_input_limit=None).provider_input_limit is None
        return
    with pytest.raises(ValueError):
        profile(**{field: value})


@pytest.mark.parametrize(
    "changes",
    [
        {"soft_target": 101},
        {"context_window": 20},
        {"output_reserve": 120},
        {"uncounted_overhead": 100},
        {"uncounted_overhead": True},
        {"uncounted_overhead": -1},
        {"paid": True},
        {"fee_scope_ref": ref("budget-scope/1")},
        {"routing_ref": ref("route/1", "public")},
        {"configuration_ref": ref("parameters/1", "public")},
        {"precision": "estimated_upper_bound"},
        {"bound_evidence_ref": ref("context-counting-bound/1")},
        {"ignored": True},
        {"schema_version": "context-budget-profile/2"},
    ],
)
def test_profile_missing_trust_or_contradictory_fields_rejected(
    changes: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        profile(**changes)


@pytest.mark.parametrize(
    "field",
    [
        "model",
        "provider",
        "routing_ref",
        "configuration_ref",
        "tokenizer_sha256",
        "template_sha256",
        "counting_method",
        "output_reserve",
    ],
)
def test_changed_model_template_counter_routing_or_limits_invalidates_measurement(
    field: str,
) -> None:
    request = selection()
    value = {
        "model": "different-model",
        "provider": "other-provider",
        "routing_ref": ref("routing/1", tag="new"),
        "configuration_ref": ref("parameters/1", tag="new"),
        "tokenizer_sha256": "d" * 64,
        "template_sha256": "e" * 64,
        "counting_method": "other-counter",
        "output_reserve": 21,
    }[field]
    changed = ContextBudgetProfile.model_validate(
        request.profile.model_copy(update={field: value})
    )
    with pytest.raises(ValueError):
        select_candidate(request.model_copy(update={"profile": changed}))


@pytest.mark.parametrize(
    "field",
    ["source", "policy_sha256", "profile_sha256", "role", "checks", "duplicate-id"],
)
def test_cross_role_source_round_policy_and_protection_binding_rejected(
    field: str,
) -> None:
    request = selection()
    changed = request.candidates[1]
    if field == "source":
        changed = changed.model_copy(
            update={"source": changed.source.model_copy(update={"revision_round": 1})}
        )
    elif field == "policy_sha256":
        changed = changed.model_copy(update={field: "f" * 64})
    elif field == "checks":
        changed = changed.model_copy(update={"checks": changed.checks[:-1]})
    elif field == "duplicate-id":
        changed = changed.model_copy(
            update={"candidate_id": request.candidates[0].candidate_id}
        )
    else:
        changed = changed.model_copy(
            update={
                "measurement": changed.measurement.model_copy(
                    update={field: "teacher" if field == "role" else "f" * 64}
                )
            }
        )
    with pytest.raises(ValueError):
        select_candidate(
            request.model_copy(update={"candidates": (request.candidates[0], changed)})
        )


@pytest.mark.parametrize(
    "change",
    [
        "private-actor",
        "private-teacher",
        "actor-as-teacher",
        "teacher-structural",
        "missing-structure-selection",
    ],
)
def test_role_specific_sources_and_Actor_only_structure_cannot_cross_Teacher(
    change: str,
) -> None:
    request = selection(
        role=(
            "teacher"
            if change in ("private-teacher", "teacher-structural")
            else "actor"
        )
    )
    if change in ("teacher-structural", "missing-structure-selection"):
        bad = {
            **request.policy.model_dump(),
            "candidate_order": ("identity", "structural_ax"),
        }
        with pytest.raises(ValueError):
            ContextProjectionPolicy.model_validate(bad)
        return
    candidate = request.candidates[0]
    key = "allowed_input_ref" if change == "private-teacher" else "turn_ref"
    source = candidate.source.model_copy(
        update={
            key: ref(
                (
                    "teacher-input/1"
                    if change == "private-teacher"
                    else "actor-public-turn/1"
                ),
                "private",
            )
        }
    )
    if change == "actor-as-teacher":
        source = source.model_copy(update={"role": "teacher"})
    with pytest.raises(ValueError):
        select_candidate(
            request.model_copy(
                update={
                    "candidates": (
                        candidate.model_copy(update={"source": source}),
                        request.candidates[1],
                    )
                }
            )
        )


def test_estimated_count_uses_verified_upper_bound_not_lower_estimate() -> None:
    p = profile(
        precision="estimated_upper_bound",
        bound_evidence_ref=ref("context-counting-bound/1"),
    )
    request = selection()
    measure = request.candidates[0].measurement.model_copy(
        update={
            "profile_sha256": p.digest,
            "precision": "estimated_upper_bound",
            "input_tokens": 70,
            "upper_bound_tokens": 101,
        }
    )
    policy = request.policy.model_copy(update={"candidate_order": ("identity",)})
    measure = measure.model_copy(update={"policy_sha256": policy.digest})
    candidate = request.candidates[0].model_copy(
        update={"measurement": measure, "policy_sha256": policy.digest}
    )
    request = ContextSelection(profile=p, policy=policy, candidates=(candidate,))
    assert not select_candidate(request).accepted
    with pytest.raises(ValueError):
        TokenMeasurement.model_validate(
            measure.model_copy(update={"precision": "exact"})
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("complete_request", False),
        ("complete_request", 1),
        ("upper_bound_tokens", 1),
        ("input_tokens", True),
        ("elapsed_seconds", float("nan")),
        ("input_ref", ref("teacher-model-input/1")),
    ],
)
def test_measurement_rejects_fragment_counts_bad_types_or_role(
    field: str, value: Any
) -> None:
    m = selection().candidates[0].measurement
    with pytest.raises(ValueError):
        TokenMeasurement.model_validate(m.model_copy(update={field: value}))


@pytest.mark.parametrize("value", [None, {}, [], "", False, (), tuple(range(5))])
def test_empty_wrong_type_or_unbounded_candidate_inputs_rejected(value: Any) -> None:
    request = selection()
    with pytest.raises(ValueError):
        ContextSelection.model_validate({**request.model_dump(), "candidates": value})


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"[]",
        b"{}",
        b"\xff",
        b"{}" + b" " * MAX_CONTEXT_METADATA,
        b'{"role":"actor","role":"teacher"}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
    ],
)
def test_bounded_wire_decoder_rejects_duplicate_nonfinite_invalid_or_missing_metadata(
    raw: bytes,
) -> None:
    with pytest.raises((ValueError, UnicodeDecodeError)):
        decode_context_budget(raw)


def test_complete_metadata_roundtrip_and_parallel_determinism_do_not_mutate_sources() -> (
    None
):
    request = selection((90, 70, 70))
    before = request.model_dump_json()
    restored = decode_context_selection(before.encode())
    assert restored == request
    assert (
        decode_context_budget(request.profile.model_dump_json().encode())
        == request.profile
    )
    expected = select_candidate(request).model_dump_json()
    with ThreadPoolExecutor(max_workers=4) as pool:
        actual = list(
            pool.map(lambda _: select_candidate(restored).model_dump_json(), range(20))
        )
    assert actual == [expected] * 20 and request.model_dump_json() == before


def test_corrupt_decision_cannot_relabel_rejection_as_prepared_or_change_scope() -> (
    None
):
    result = select_candidate(selection((101,)))
    bad = {**result.model_dump(mode="json"), "accepted": True}
    with pytest.raises(ValueError):
        decode_context_decision(json.dumps(bad).encode())
    good = select_candidate(selection())
    bad = {**good.model_dump(mode="json"), "reason_code": "input_budget_exceeded"}
    with pytest.raises(ValueError):
        decode_context_decision(json.dumps(bad).encode())


def test_policy_digest_is_part_of_count_identity_and_decision_freezes_complete_selection() -> (
    None
):
    request = selection()
    changed = request.candidates[1].model_copy(
        update={
            "measurement": request.candidates[1].measurement.model_copy(
                update={"policy_sha256": "0" * 64}
            )
        }
    )
    with pytest.raises(ValueError):
        select_candidate(
            request.model_copy(update={"candidates": (request.candidates[0], changed)})
        )
    decision = select_candidate(request)
    assert decision.selection_sha256 == request.digest
    assert decision.policy_sha256 == request.policy.digest
    assert decision.profile_sha256 == request.profile.digest


def test_Actor_full_AX_noop_does_not_grant_structural_reduction_scope() -> None:
    from lab_generate_skill.domain.actor_projection import FullAxProjection

    request = selection((90, 70), kinds=("identity", "structural_ax"), structural=True)
    with pytest.raises(ValueError):
        ContextProjectionPolicy.model_validate(
            request.policy.model_copy(update={"actor_projection": FullAxProjection()})
        )


@pytest.mark.parametrize(
    "missing",
    [
        "schema_version",
        "role",
        "model",
        "provider",
        "routing_ref",
        "configuration_ref",
        "tokenizer_sha256",
        "template_sha256",
        "counting_method",
        "precision",
        "bound_evidence_ref",
        "context_window",
        "output_reserve",
        "input_limit",
        "provider_input_limit",
        "soft_target",
        "uncounted_overhead",
        "paid",
        "fee_scope_ref",
    ],
)
def test_wire_budget_requires_every_frozen_profile_field(missing: str) -> None:
    raw = profile().model_dump(mode="json")
    del raw[missing]
    with pytest.raises(ValueError):
        decode_context_budget(json.dumps(raw).encode())


def test_valid_profile_with_duplicate_field_is_rejected_before_value_validation() -> (
    None
):
    raw = profile().model_dump_json().encode()
    raw = raw[:-1] + b',"output_reserve":20}'
    with pytest.raises(ValueError, match="Duplicate JSON field"):
        decode_context_budget(raw)
