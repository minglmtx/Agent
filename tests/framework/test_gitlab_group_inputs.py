"""Original source/public separation, strict types and exact native row coverage."""

import hashlib
import json
from typing import Any
import pytest
from lab_generate_skill.bootstrap.gitlab_group import load_group_inputs
from lab_generate_skill.bootstrap.gitlab_group_state import load_group_state
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.sites.gitlab.tasks.group_spec import (
    GroupRequirements,
    GroupSpec,
)
from lab_generate_skill.sites.gitlab.tasks.group_state import GroupNativeState
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.actor.prompting import prepare_actor
from observation_fixtures import sample_observation
from test_actor_protocol import turn
from gitlab_group_fixtures import (
    FIXTURE,
    reference,
    public_task,
    selected_spec,
    native_state,
)


def test_exact_original_contract_is_unadmitted_repeatable_and_private() -> None:
    raw = FIXTURE.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "acd7e87bdbfbe2d18d093135bcbb1940d7cf259a13d7665511be8bc3437ce750"
    )
    private = load_group_inputs(raw, reference(raw), public_task())
    assert (
        private
        == selected_spec()
        == load_group_inputs(raw, reference(raw), public_task())
    )
    assert private.admission == "unverified" and private.requirements.top_level is False
    assert (
        private.requirements.settings is not None
        and private.requirements.settings.setup_for_company is True
    )
    prompts = []
    for marker in ("private-group-one", "private-group-two"):
        native = json.loads(raw)
        native["admission_result"] = marker
        data = json.dumps(native).encode()
        assert (
            load_group_inputs(data, reference(data), public_task()).native_goal
            == public_task().goal
        )
        original, observation = turn(), sample_observation(public_task().identity)
        prompt = prepare_actor(
            ActorPublicTurn(
                task=public_task(),
                skill=original.skill,
                observation=ResolvedObservation(
                    record=observation, text=observation.text
                ),
                history=(),
                memory=original.memory,
            )
        ).model_dump_json()
        assert (
            marker not in prompt
            and "native_contract_ref" not in prompt
            and "setup_for_company" not in prompt
        )
        prompts.append(prompt)
    assert prompts[0] == prompts[1]


@pytest.mark.parametrize(
    "settings",
    [
        None,
        {"setup_for_company": True},
        {"setup_for_company": False},
        {"jobs_to_be_done": 0},
        {"jobs_to_be_done": 2},
        {"jobs_to_be_done": 3},
        {"setup_for_company": True, "jobs_to_be_done": 3},
    ],
)
@pytest.mark.parametrize("path", [None, "development-team"])
def test_canonical_private_input_preserves_declared_requirements(
    settings: Any, path: str | None
) -> None:
    native = json.loads(FIXTURE.read_bytes())
    requirements = native["group_creation"]
    requirements.pop("settings", None)
    if settings is not None:
        requirements["settings"] = settings
    if path is not None:
        requirements["path"] = path
    raw = json.dumps(native).encode()
    spec = load_group_inputs(raw, reference(raw), public_task())
    encoded = spec.model_dump_json()
    assert json.loads(encoded)["requirements"] == requirements
    restored = GroupSpec.model_validate_json(encoded)
    assert restored == spec and restored.model_dump_json() == encoded
    assert GroupSpec.model_validate(spec).model_dump_json() == encoded


@pytest.mark.parametrize(
    "field,value",
    [
        ("group_creation", {}),
        ("group_creation", None),
        ("group_creation", []),
        ("heldout_quarantine", True),
        ("eligible_for_training", True),
        ("task_text_changed", True),
        ("api_calls", False),
        ("api_calls", 1),
        ("source_task_id", "foreign"),
        ("task_id", "derived"),
        ("start_path", "/"),
        ("source_trace_ids", []),
        ("extra", "unknown"),
        ("completion", {"family": "other"}),
    ],
)
def test_bad_original_contract_refused(field: str, value: Any) -> None:
    data = json.loads(FIXTURE.read_bytes())
    data[field] = value
    raw = json.dumps(data).encode()
    with pytest.raises(EvidenceIntegrityError):
        load_group_inputs(raw, reference(raw), public_task())


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "   "),
        ("name", True),
        ("name", []),
        ("visibility_level", False),
        ("visibility_level", "0"),
        ("visibility_level", 1),
        ("top_level", 0),
        ("top_level", None),
        ("path", None),
        ("path", ""),
        ("path", "../x"),
        ("settings", {}),
        ("settings", None),
        ("settings", {"setup_for_company": 1}),
        ("settings", {"setup_for_company": None}),
        ("settings", {"jobs_to_be_done": False}),
        ("settings", {"jobs_to_be_done": 1}),
        ("settings", {"unknown": True}),
    ],
)
def test_group_requirements_keep_exact_native_types(field: str, value: Any) -> None:
    requirements = json.loads(FIXTURE.read_bytes())["group_creation"]
    requirements[field] = value
    with pytest.raises(ValueError):
        GroupRequirements.model_validate(requirements)


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate-group",
        "duplicate-member",
        "duplicate-settings",
        "wrong-id",
        "wrong-type",
        "missing",
        "foreign",
        "old",
        "json-duplicate",
        "nan",
        "empty",
        "broken",
    ],
)
def test_native_wire_never_upgrades_missing_foreign_or_ambiguous_facts(
    fault: str,
) -> None:
    data = native_state().model_dump(mode="json")
    if fault.startswith("duplicate-"):
        key = {
            "duplicate-group": "groups",
            "duplicate-member": "members",
            "duplicate-settings": "settings",
        }[fault]
        data[key].append(data[key][0])
    elif fault == "wrong-id":
        data["groups"][0]["id"] = True
    elif fault == "wrong-type":
        data["groups"] = {}
    elif fault == "missing":
        data.pop("settings")
    elif fault == "foreign":
        data["task"]["source_task_id"] = "foreign"
    elif fault == "old":
        data["schema_version"] = "gitlab-group-state/0"
    raw = json.dumps(data).encode()
    if fault == "json-duplicate":
        raw = b'{"user":null,' + raw[1:]
    elif fault == "nan":
        raw = raw.replace(b'"id": 1,', b'"id": NaN,', 1)
    elif fault == "empty":
        raw = b""
    elif fault == "broken":
        raw = b'{"groups":'
    with pytest.raises((ValueError, EvidenceIntegrityError)):
        load_group_state(raw, selected_spec())


def test_empty_sql_collections_are_complete_facts_not_missing_fields() -> None:
    data = native_state().model_dump(mode="json")
    data.update(groups=[], members=[], settings=[])
    value = GroupNativeState.model_validate_json(json.dumps(data))
    assert load_group_state(value.model_dump_json().encode(), selected_spec()) == value
