"""Actual public/private binding, input byte and native integer boundaries."""

import json
from typing import Any, cast
import pytest
from lab_generate_skill.bootstrap.gitlab_group import load_group_inputs
from lab_generate_skill.bootstrap.gitlab_group_state import load_group_state
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from gitlab_group_fixtures import (
    FIXTURE,
    public_task,
    reference,
    selected_spec,
    native_state,
)


@pytest.mark.parametrize(
    "field,value",
    [
        ("goal", "Different goal"),
        ("start_url", "http://127.0.0.1:18080/"),
        ("start_url", "http://other.example:18080/groups/new"),
        ("start_url", "http://127.0.0.1:999/groups/new"),
        ("start_url", "http://127.0.0.1:18080/groups/new?target=hidden"),
        ("start_url", "http://127.0.0.1:18080/groups/new#other"),
        ("split", "test"),
        ("family", "profile_ssh_key"),
        ("contract_version", 2),
        ("task_id", "foreign"),
    ],
)
def test_public_scope_or_start_cannot_silently_select_another_family(
    field: str, value: Any
) -> None:
    data = public_task().model_dump(mode="json")
    target = (
        data["identity"]
        if field in ("split", "family", "contract_version", "task_id")
        else data
    )
    target[field] = value
    public = PublicTask.model_validate_json(json.dumps(data))
    raw = FIXTURE.read_bytes()
    with pytest.raises(EvidenceIntegrityError):
        load_group_inputs(raw, reference(raw), public)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "0" * 64),
        ("size_bytes", 1),
        ("visibility", "public"),
        ("content_schema", "gitlab-native-contract/0"),
        ("media_type", "text/plain"),
    ],
)
def test_original_private_bytes_and_ref_must_agree(field: str, value: Any) -> None:
    raw = FIXTURE.read_bytes()
    data = reference(raw).model_dump(mode="json")
    data[field] = value
    changed = EvidenceRef.model_validate_json(json.dumps(data))
    with pytest.raises(EvidenceIntegrityError):
        load_group_inputs(raw, changed, public_task())


@pytest.mark.parametrize("raw", [None, True, 1, [], {}, b"", b'{"task_id":'])
def test_empty_partial_or_wrong_type_original_input_is_refused(raw: object) -> None:
    ref = reference(raw if type(raw) is bytes and raw else FIXTURE.read_bytes())
    with pytest.raises(EvidenceIntegrityError):
        load_group_inputs(cast(bytes, raw), ref, public_task())


@pytest.mark.parametrize("value", [0, -1, 9223372036854775808, True, 1.5, "1", None])
def test_native_identity_extremes_are_not_coerced(value: Any) -> None:
    data = native_state().model_dump(mode="json")
    data["groups"][0]["id"] = value
    with pytest.raises(ValueError):
        load_group_state(json.dumps(data).encode(), selected_spec())
