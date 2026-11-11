"""Public observation edge cases; no browser execution or baseline claims."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation import (
    BrowserTab,
    Observation,
    ObservationArtifact,
    ResolvedObservation,
)
from observation_fixtures import sample_observation
from test_core_contracts import identity, reference


def text_reference(text: str) -> EvidenceRef:
    raw = text.encode()
    digest = hashlib.sha256(raw).hexdigest()
    return reference("public", "observation-text/1").model_copy(
        update={
            "uri": "cas://sha256/" + digest,
            "sha256": digest,
            "size_bytes": len(raw),
        }
    )


@pytest.mark.parametrize("text", ["", "  \n\t", "中文地图\nCafé 🗺️", "a" * 65536])
def test_exact_text_roundtrip_including_empty_and_unicode(text: str) -> None:
    observation = Observation.model_validate(
        sample_observation(identity()).model_copy(update={"text": text})
    )
    assert Observation.model_validate_json(observation.model_dump_json()) == observation
    assert ResolvedObservation(record=observation, text=text).text == text
    observation.check_initial(identity(), "context")


@pytest.mark.parametrize(
    "update",
    [
        {"sequence": -1},
        {"sequence": True},
        {"sequence": 0.0},
        {"sequence": "0"},
        {"tabs": ()},
        {"active_tab_id": "missing"},
        {"text": None},
        {"text": 42},
        {"text": "\ud800"},
        {"last_action_error": None},
        {"captured_at": datetime(2026, 1, 1)},
        {"state": "error"},
        {"state": "unavailable"},
        {"state": "ready", "error_code": "failed"},
        {"private_spec_ref": "secret"},
        {"schema_version": "observation/0"},
        {"text_ref": reference("private", "observation-text/1")},
        {"text_ref": reference("public", "wrong/1"), "text": None},
        {"text_ref": text_reference("duplicate")},
        {
            "artifacts": (
                ObservationArtifact(name="screen", reference=reference("public")),
            )
            * 2
        },
    ],
)
def test_invalid_observation_rejected(update: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(
            sample_observation(identity()).model_copy(update=update)
        )


def test_tabs_require_unique_ids_but_allow_same_url() -> None:
    value = sample_observation(identity())
    with pytest.raises(ValidationError):
        Observation.model_validate(value.model_copy(update={"tabs": value.tabs * 2}))
    other = value.tabs[0].model_copy(update={"tab_id": "other"})
    assert (
        len(
            Observation.model_validate(
                value.model_copy(update={"tabs": (*value.tabs, other)})
            ).tabs
        )
        == 2
    )


@pytest.mark.parametrize(
    "url",
    [
        "about:blank",
        "https://example.test/path?q=1",
        "chrome-error://chromewebdata/",
        "blob:https://example.test/123",
    ],
)
def test_observed_non_http_error_or_blank_locations_are_preserved(url: str) -> None:
    assert BrowserTab(tab_id="tab", url=url, title="").url == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "relative/path",
        "https://user:pass@example.test/",
        "https:///missing",
        "https://example.test/\n",
        "https://example.test/\x00",
        "https://example.test/\ud800",
    ],
)
def test_invalid_or_credential_bearing_url_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        BrowserTab(tab_id="tab", url=url, title="")


@pytest.mark.parametrize("state", ["loading", "error", "unavailable"])
def test_nonready_facts_are_recordable_but_not_initial(state: str) -> None:
    update: dict[str, object] = {"state": state, "text": None}
    if state != "loading":
        update.update(error_code="CAPTURE_FAILED", tabs=(), active_tab_id=None)
    observation = Observation.model_validate(
        sample_observation(identity()).model_copy(update=update)
    )
    assert ResolvedObservation(record=observation, text=None).text is None
    with pytest.raises(ValueError):
        observation.check_initial(identity(), "context")


@pytest.mark.parametrize("change", ["task", "context", "sequence", "action_error"])
def test_initial_binding_cannot_accept_later_or_other_observation(change: str) -> None:
    value = sample_observation(identity())
    changes: dict[str, object] = {
        "task": identity().model_copy(update={"task_id": "other"}),
        "context": "other",
        "sequence": 1,
        "action_error": "Click failed",
    }
    field = {"context": "context_id", "action_error": "last_action_error"}.get(
        change, change
    )
    value = Observation.model_validate(
        value.model_copy(update={field: changes[change]})
    )
    with pytest.raises(ValueError):
        value.check_initial(identity(), "context")


def test_referenced_and_artifact_only_content_preserve_exact_bytes() -> None:
    text = "中文\r\n"
    value = Observation.model_validate(
        sample_observation(identity()).model_copy(
            update={"text": None, "text_ref": text_reference(text)}
        )
    )
    assert ResolvedObservation(record=value, text=text).record == value
    for wrong in (None, "中文\n", "other"):
        with pytest.raises(ValidationError):
            ResolvedObservation(record=value, text=wrong)
    artifact = ObservationArtifact(
        name="screenshot", reference=reference("public", "image/1")
    )
    visual = Observation.model_validate(
        value.model_copy(update={"text_ref": None, "artifacts": (artifact,)})
    )
    assert ResolvedObservation(record=visual, text=None).record.artifacts == (artifact,)
    with pytest.raises(ValidationError):
        ObservationArtifact(name="private", reference=reference("private"))


def test_captured_time_normalizes_to_utc_without_changing_instant() -> None:
    local = datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))
    value = Observation.model_validate(
        sample_observation(identity()).model_copy(update={"captured_at": local})
    )
    assert value.captured_at == local and value.captured_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("bad", [None, {}, [], True, 42])
def test_wrong_root_type_rejected(bad: object) -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(bad)


def test_initial_method_revalidates_forged_equal_scalar() -> None:
    observation = sample_observation(identity()).model_copy(update={"sequence": False})
    with pytest.raises(ValidationError):
        observation.check_initial(identity(), "context")
