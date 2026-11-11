"""Selected Map boundary and actual Actor public projection; no native effects."""

from pathlib import Path
import hashlib
import json
from typing import Any
import pytest
from lab_generate_skill.bootstrap.map_native_overlay import load_overlay_inputs
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.observation import (
    ResolvedObservation,
    BrowserTab,
    Observation,
)
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.sites.map.tasks.overlay_spec import SOURCE, START, GOAL
from observation_fixtures import sample_observation
from test_actor_protocol import turn

FIXTURE = Path(__file__).parent / "fixtures/map-native-overlay.json"


def reference(raw: bytes, **updates: Any) -> EvidenceRef:
    return EvidenceRef.model_validate(
        dict(
            uri="cas:map-overlay",
            sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
            media_type="application/json",
            content_schema="map-native-contract/1",
            visibility="private",
            producer="test",
        )
        | updates
    )


def public_task(**updates: Any) -> PublicTask:
    return PublicTask.model_validate(
        dict(
            identity=TaskIdentity(
                source_task_id=SOURCE,
                task_id=SOURCE,
                split="train",
                site="map",
                family="native_route_map_data",
                contract_version=1,
            ),
            goal=GOAL,
            start_url="http://127.0.0.1:18080" + START,
            allowed_actions=("click", "fill", "scroll", "send_msg_to_user"),
        )
        | updates
    )


def test_exact_original_and_repeat_without_admission_or_route_rewrite() -> None:
    raw = FIXTURE.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "50356bbd0811eaac447f9bbef29a348a552dc38c2478a1cbec13464f1719cb2d"
    )
    result = load_overlay_inputs(raw, reference(raw), public_task())
    assert result.private_spec.admission == "unverified"
    assert result.private_spec.original_start_path == START
    assert result.public_task.goal == GOAL
    assert load_overlay_inputs(raw, reference(raw), public_task()) == result


def test_actual_actor_projection_excludes_private_provenance() -> None:
    prompts = []
    for marker in ("private-reference-one", "private-reference-two"):
        native = json.loads(FIXTURE.read_bytes())
        native["admission_result"] = marker
        raw = json.dumps(native).encode()
        value = load_overlay_inputs(raw, reference(raw), public_task())
        original = turn()
        observed_data = sample_observation(value.public_task.identity).model_dump(
            mode="python"
        )
        observed_data["tabs"] = (
            BrowserTab(
                tab_id="main", url=value.public_task.start_url, title="Public map"
            ),
        )
        observed = Observation.model_validate(observed_data)
        prompt = prepare_actor(
            ActorPublicTurn(
                task=value.public_task,
                skill=original.skill,
                observation=ResolvedObservation(record=observed, text=observed.text),
                history=(),
                memory=original.memory,
            )
        )
        text = prompt.model_dump_json()
        assert (
            marker not in text
            and "cas:map-overlay" not in text
            and "admission_result" not in text
        )
        assert GOAL in text and START in text
        prompts.append(text)
    assert prompts[0] == prompts[1]


@pytest.mark.parametrize(
    "path,value",
    [
        ("source_task_id", "other"),
        ("task_id", "other"),
        ("domain", "reddit"),
        ("eligible_for_training", True),
        ("eligible_for_training", 0),
        ("heldout_quarantine", True),
        ("heldout_quarantine", None),
        ("goal", "Enable Map Notes"),
        ("start_path", "/"),
        ("recorded_start_paths", []),
        ("recorded_start_paths", [START, START]),
        ("recorded_start_urls", ["https://old.example" + START]),
        ("recorded_start_urls", ["http://user:password@old.example" + START]),
        ("recorded_start_urls", ["http://old.example/"]),
        ("source_aliases", []),
        ("source_trace_ids", ["gobrowse:2346"]),
        ("source_trace_ids", ["gobrowse:2346", "gobrowse:2346"]),
        ("admission_result", ""),
        ("admission_result", None),
        ("completion.kind", "generic_local_layer_transition"),
        ("completion.allowed_local_overlay_labels", ["Map Notes"]),
        ("completion.allowed_local_overlay_labels", ["Map Data", "Map Data"]),
        ("completion.normal_admitted", True),
        ("completion.normal_admitted", 0),
        ("completion.preserve_original_area", True),
        ("completion.retain_original_native_route", False),
        ("completion.semantic_review_required", False),
        ("completion.no_private_positive_steps_in_public_goal", False),
        ("completion.original_goal", "changed"),
        ("completion.version", "v2"),
        ("map_native_layer.native_batch_seconds", 299),
        ("map_native_layer.native_batch_seconds", 301),
        ("map_native_layer.native_batch_seconds", True),
        ("map_native_layer.native_batch_seconds", 300.0),
        ("map_native_layer.version", "v2"),
        ("map_native_layer", None),
        ("extra", "unregistered"),
        ("map_export", {}),
    ],
)
def test_changed_native_scope_is_rejected(path: str, value: Any) -> None:
    native = json.loads(FIXTURE.read_bytes())
    target = native
    fields = path.split(".")
    for field in fields[:-1]:
        target = target[field]
    target[fields[-1]] = value
    raw = json.dumps(native).encode()
    with pytest.raises(EvidenceIntegrityError):
        load_overlay_inputs(raw, reference(raw), public_task())


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"null",
        b"[]",
        b"{}",
        b"true",
        b"{",
        b'{"domain":"map","domain":"map"}',
        b"x" * (1024 * 1024 + 1),
    ],
)
def test_empty_wrong_type_duplicate_malformed_and_oversize(raw: bytes) -> None:
    with pytest.raises(EvidenceIntegrityError):
        load_overlay_inputs(raw, reference(raw), public_task())


@pytest.mark.parametrize("case", ["hash", "size", "visibility", "schema", "media"])
def test_reference_integrity_before_binding(case: str) -> None:
    raw = FIXTURE.read_bytes()
    choices: dict[str, dict[str, Any]] = {
        "hash": {"sha256": "0" * 64},
        "size": {"size_bytes": len(raw) + 1},
        "visibility": {"visibility": "public"},
        "schema": {"content_schema": "other/1"},
        "media": {"media_type": "text/plain"},
    }
    with pytest.raises(EvidenceIntegrityError):
        load_overlay_inputs(raw, reference(raw, **choices[case]), public_task())


@pytest.mark.parametrize(
    "case",
    [
        "goal",
        "host",
        "port",
        "path",
        "route",
        "fragment",
        "action",
        "split",
        "family",
        "source",
        "version",
    ],
)
def test_public_binding_mismatch(case: str) -> None:
    original = public_task()
    data = original.model_dump(mode="python")
    if case == "goal":
        data["goal"] = "changed"
    elif case == "host":
        data["start_url"] = "http://outside.example:18080" + START
    elif case == "port":
        data["start_url"] = "http://127.0.0.1:80" + START
    elif case == "path":
        data["start_url"] = "http://127.0.0.1:18080/"
    elif case == "route":
        data["start_url"] = original.start_url.replace("40.7830", "40.0000")
    elif case == "fragment":
        data["start_url"] = original.start_url.split("#")[0]
    elif case == "action":
        data["allowed_actions"] = ("click",)
    else:
        field, value = {
            "split": ("split", "test"),
            "family": ("family", "generic_overlay"),
            "source": ("source_task_id", "other"),
            "version": ("contract_version", 2),
        }[case]
        data["identity"][field] = value
    raw = FIXTURE.read_bytes()
    with pytest.raises(EvidenceIntegrityError):
        load_overlay_inputs(raw, reference(raw), PublicTask.model_validate(data))


@pytest.mark.parametrize("port", [1024, 65535])
def test_allocated_port_boundaries_preserve_original_path(port: int) -> None:
    raw = FIXTURE.read_bytes()
    public = public_task(start_url=f"http://127.0.0.1:{port}" + START)
    assert load_overlay_inputs(raw, reference(raw), public).public_task == public
