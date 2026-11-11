"""Exact new consumer variant and same preparation API; no native effects."""

import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.reddit_native_image import load_image_inputs
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.sites.reddit.tasks.image_contract_variant import (
    FORUM_CONTRACT_SHA256,
)
from lab_generate_skill.sites.reddit.tasks.image_policy import image_initial_spec
from reddit_forum_source_fixtures import CONTRACT, public
from test_reddit_image_inputs import reference
from reddit_preparation_native import RedditPreparation
from test_reddit_live_preparation import private_configuration
from site_resource_fixtures import resource_case


def test_original_pinned_v2_keeps_native_derivative_forum_start_and_both_photos() -> (
    None
):
    raw = CONTRACT.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FORUM_CONTRACT_SHA256
    value = load_image_inputs(raw, reference(raw), public())
    assert load_image_inputs(raw, reference(raw), public()) == value
    assert value.private_spec.parameters.forum == "EarthPorn"
    assert value.private_spec.parameters.title == "Landscape Photo"
    assert value.private_spec.admission == "unverified"
    assert value.public_task.start_url.endswith("/forums/all")
    assert "/anvme/" not in value.public_task.model_dump_json()


@pytest.mark.parametrize(
    "change",
    [
        "missing-resolution",
        "resolution-type",
        "resolution-flag",
        "other-source",
        "trace",
        "trace-line",
        "goal-version",
        "wrong-start",
        "extra",
        "empty",
        "null",
        "bytes",
    ],
)
def test_changed_v2_contract_refused_without_effects(change: str) -> None:
    n: Any = json.loads(CONTRACT.read_bytes())
    if change == "missing-resolution":
        del n["object_resolution"]
    elif change == "resolution-type":
        n["object_resolution"] = []
    elif change == "resolution-flag":
        n["object_resolution"]["uses_late_actor_to_reinterpret_original"] = 1
    elif change == "other-source":
        n["source_task_id"] = "292-original"
    elif change == "trace":
        n["source_trace_ids"] = []
    elif change == "trace-line":
        n["recorded_trace_evidence"][0]["line_number"] = 0
    elif change == "goal-version":
        n["goal_revision"]["version"] = "native-media-cpu-v1"
    elif change == "wrong-start":
        n["start_path"] = "/submit"
    elif change == "extra":
        n["unknown"] = "ignored"
    elif change == "empty":
        n = {}
    elif change == "null":
        n = None
    else:
        n["public_parameters"]["image_bytes"] = True
    raw = json.dumps(n).encode()
    with pytest.raises(EvidenceIntegrityError):
        load_image_inputs(raw, reference(raw), public())


@pytest.mark.parametrize(
    "suffix", ["submit", "forums/all?x=1", "forums/all#x", "f/EarthPorn", "forums/all/"]
)
def test_public_start_cannot_be_substituted(suffix: str) -> None:
    raw = CONTRACT.read_bytes()
    with pytest.raises(EvidenceIntegrityError):
        load_image_inputs(
            raw,
            reference(raw),
            public().model_copy(
                update={"start_url": "http://127.0.0.1:18080/" + suffix}
            ),
        )


def test_new_consumer_uses_same_preparation_bindings_without_site_or_actor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = resource_case(tmp_path, monkeypatch, config=private_configuration(tmp_path))
    task = public("http://127.0.0.1:12001/")
    native = RedditPreparation(
        c,
        "http://127.0.0.1:12001/",
        state_spec=image_initial_spec(task.identity),
        native_input=CONTRACT.read_bytes(),
        public_input=task,
    )
    assert (
        native.public == task
        and native.bindings.load(native.binding_ref, c.op) == native.binding
    )
    assert native.image_spec.native_contract_ref.sha256 == FORUM_CONTRACT_SHA256
    assert native.request is None and native.result is None and not c.channels
