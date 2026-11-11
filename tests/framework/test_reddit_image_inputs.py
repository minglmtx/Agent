"""Selected original native media input; no website, upload or training grant."""

from pathlib import Path
import hashlib
import json
from typing import Any
import pytest
from lab_generate_skill.bootstrap.reddit_native_image import load_image_inputs
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.sites.reddit.tasks.image_parameters import PHOTOS
from lab_generate_skill.sites.reddit.tasks.image_spec import OUTPUT_REQUIREMENTS
from observation_fixtures import sample_observation
from test_actor_protocol import turn

FIXTURE = Path(__file__).parent / "fixtures/reddit-native-image.json"


def reference(raw: bytes, **updates: Any) -> EvidenceRef:
    return EvidenceRef(
        **dict(
            uri="cas:reddit-native-image",
            sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
            media_type="application/json",
            content_schema="reddit-native-contract/1",
            visibility="private",
            producer="test",
            **updates,
        )
    )


def public_task() -> PublicTask:
    n = json.loads(FIXTURE.read_bytes())
    files = [
        dict(
            path=p.relative_file,
            sha256=p.sha256,
            bytes=p.bytes,
            description=p.description,
        )
        for p in PHOTOS
    ]
    goal = (
        n["goal"]
        + "\nPublic task parameters: "
        + json.dumps(n["public_parameters"], ensure_ascii=False, sort_keys=True)
        + "\nAvailable local photographs: "
        + json.dumps(files, ensure_ascii=False, sort_keys=True)
    )
    return PublicTask(
        identity=TaskIdentity(
            source_task_id=n["source_task_id"],
            task_id=n["task_id"],
            split="train",
            site="reddit",
            family="native_image_submission",
            contract_version=1,
        ),
        goal=goal,
        start_url="http://127.0.0.1:18080/submit",
        allowed_actions=("click", "fill", "upload_file", "send_msg_to_user"),
        output_requirements=OUTPUT_REQUIREMENTS,
    )


def test_original_contract_and_both_logical_public_photos_are_exact_and_unadmitted() -> (
    None
):
    raw = FIXTURE.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "9519ac9ca77e62d2e416a79cb55c4ddaae31cdf55da70dcff7e2b79493c67861"
    )
    result = load_image_inputs(raw, reference(raw), public_task())
    assert result.private_spec.admission == "unverified"
    assert (
        result.private_spec.parameters.image_fixture
        == "assets/fixed-beach-sunset-photo.jpg"
    )
    assert result.private_spec.parameters.title == "Beautiful Sunset at the Beach"
    assert load_image_inputs(raw, reference(raw), public_task()) == result
    assert len(PHOTOS) == 2 and "/anvme/" not in result.public_task.model_dump_json()


def test_actual_actor_prompt_contains_both_public_files_without_private_reference_or_host_path() -> (
    None
):
    native = json.loads(FIXTURE.read_bytes())
    prompts = []
    for marker in ("private-one", "private-two"):
        native["source_trace_ids"] = [marker]
        native["goal_revision"]["reason"] = marker
        raw = json.dumps(native).encode()
        value = load_image_inputs(raw, reference(raw), public_task())
        original, observation = turn(), sample_observation(value.public_task.identity)
        prompt = prepare_actor(
            ActorPublicTurn(
                task=value.public_task,
                skill=original.skill,
                observation=ResolvedObservation(
                    record=observation, text=observation.text
                ),
                history=(),
                memory=original.memory,
            )
        )
        text = prompt.model_dump_json()
        assert (
            marker not in text
            and "admission_result" not in text
            and "cas:reddit" not in text
        )
        assert all(p.relative_file in text and p.sha256 in text for p in PHOTOS)
        assert "/anvme/" not in text and "upload_file" in text
        prompts.append(text)
    assert prompts[0] == prompts[1]


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "null",
        "list",
        "missing",
        "extra",
        "scope",
        "trained",
        "flag_type",
        "params_empty",
        "params_none",
        "title",
        "forum",
        "body",
        "file",
        "sha",
        "bytes_bool",
        "bytes_zero",
        "bytes_large",
        "dimensions",
        "dim_bool",
        "private_params",
        "driver",
        "lineage",
        "start",
        "trace",
    ],
)
def test_native_invalid_input_rejected_before_effects(case: str) -> None:
    n: Any = json.loads(FIXTURE.read_bytes())
    if case in ("empty", "null", "list"):
        n = {} if case == "empty" else None if case == "null" else []
    elif case == "missing":
        del n["goal_revision"]
    elif case == "extra":
        n["new_dispatch"] = "module.name"
    elif case == "scope":
        n["heldout_quarantine"] = True
    elif case == "trained":
        n["training_admitted"] = True
    elif case == "flag_type":
        n["eligible_for_training"] = 0
    elif case == "params_empty":
        n["public_parameters"] = {}
    elif case == "params_none":
        n["public_parameters"] = None
    elif case == "title":
        n["public_parameters"]["title"] = "\n"
    elif case == "forum":
        n["public_parameters"]["forum"] = []
    elif case == "body":
        del n["public_parameters"]["body"]
    elif case == "file":
        n["public_parameters"]["image_fixture"] = "../../private"
    elif case == "sha":
        n["public_parameters"]["image_sha256"] = "0" * 64
    elif case == "bytes_bool":
        n["public_parameters"]["image_bytes"] = True
    elif case == "bytes_zero":
        n["public_parameters"]["image_bytes"] = 0
    elif case == "bytes_large":
        n["public_parameters"]["image_bytes"] = 2**63
    elif case == "dimensions":
        n["public_parameters"]["image_dimensions"] = [1280]
    elif case == "dim_bool":
        n["public_parameters"]["image_dimensions"] = [True, 1280]
    elif case == "private_params":
        n["public_parameters"]["reference"] = "private"
    elif case == "driver":
        n["driver_key"] = "other"
    elif case == "lineage":
        n["goal_revision"]["derived_goal"] = "other"
    elif case == "start":
        n["recorded_start_urls"] = ["http://user:password@remote/submit"]
    elif case == "trace":
        n["source_trace_ids"] = []
    raw = json.dumps(n).encode()
    with pytest.raises(EvidenceIntegrityError):
        load_image_inputs(raw, reference(raw), public_task())


@pytest.mark.parametrize(
    "case",
    [
        "goal",
        "file",
        "start",
        "remote",
        "port",
        "query",
        "family",
        "split",
        "source",
        "no_upload",
        "output",
    ],
)
def test_explicit_public_binding_rejects_other_meaning_or_scope(case: str) -> None:
    values = public_task().model_dump()
    if case == "goal":
        values["goal"] = "Submit an image"
    elif case == "file":
        values["goal"] = values["goal"].replace(
            "assets/fixed-beach-sunset-photo.jpg", "/tmp/other.jpg"
        )
    elif case == "start":
        values["start_url"] = "http://127.0.0.1:18080/"
    elif case == "remote":
        values["start_url"] = "http://remote:18080/submit"
    elif case == "port":
        values["start_url"] = "http://127.0.0.1:80/submit"
    elif case == "query":
        values["start_url"] += "?secret=1"
    elif case == "family":
        values["identity"]["family"] = "post_reading"
    elif case == "split":
        values["identity"]["split"] = "test"
    elif case == "source":
        values["identity"]["source_task_id"] = "foreign"
    elif case == "no_upload":
        values["allowed_actions"] = ("click", "send_msg_to_user")
    elif case == "output":
        values["output_requirements"] = ()
    raw = FIXTURE.read_bytes()
    with pytest.raises(EvidenceIntegrityError):
        load_image_inputs(raw, reference(raw), PublicTask.model_validate(values))


@pytest.mark.parametrize(
    "case", ["sha", "public", "schema", "duplicate", "not_bytes", "empty", "large"]
)
def test_original_bytes_reference_and_decoder_are_bounded(case: str) -> None:
    raw: Any = FIXTURE.read_bytes()
    ref = reference(raw)
    if case == "sha":
        ref = ref.model_copy(update={"sha256": "0" * 64})
    elif case == "public":
        ref = ref.model_copy(update={"visibility": "public"})
    elif case == "schema":
        ref = ref.model_copy(update={"content_schema": "gitlab-native-contract/1"})
    elif case == "duplicate":
        raw = b'{"domain":"reddit","domain":"reddit"}'
        ref = reference(raw)
    elif case == "not_bytes":
        raw = bytearray(raw)
    elif case == "empty":
        raw = b""
        ref = reference(raw)
    elif case == "large":
        raw = b" " * (1024 * 1024 + 1)
        ref = reference(raw)
    with pytest.raises(EvidenceIntegrityError):
        load_image_inputs(raw, ref, public_task())
