"""Exact public fixture scope, original controls/hierarchy and frozen input budget."""

import hashlib
import importlib
import json
import os
from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.actor.rails_diagnostic_ax import diagnostic_ax_view
from lab_generate_skill.bootstrap.actor_projection import build_actor_projection
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.actor_projection import (
    FullAxProjection,
    MapRailsDiagnosticProjection,
    actor_projection_configuration,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.observation import ResolvedObservation
from map_actor_view_fixtures import original_turn, ROOT


@pytest.mark.parametrize("index", range(12))
def test_previous_public_inputs_retain_exact_original_baseline_bytes(
    index: int,
) -> None:
    turn, original = original_turn(index)
    assert prepare_actor(turn).model_dump_json() == original.model_dump_json()
    project = build_actor_projection(MapRailsDiagnosticProjection())
    assert project(turn).model_dump_json() == original.model_dump_json()


def test_original_failed_input_full_AX_preserved_and_selected_view_fits_same_budget() -> (
    None
):
    transformers = importlib.import_module("transformers")

    turn, original = original_turn()
    assert prepare_actor(turn).model_dump_json() == original.model_dump_json()
    data = json.loads((ROOT / "map-actor-budget-fixtures.json").read_bytes())
    for pin in data["tokenizer_pins"]:
        raw = (Path(data["tokenizer_root"]) / pin["path"]).read_bytes()
        assert (
            len(raw) == pin["size_bytes"]
            and hashlib.sha256(raw).hexdigest() == pin["sha256"]
        )
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        data["tokenizer_root"], local_files_only=True, trust_remote_code=False
    )
    original_bytes = turn.observation.model_dump_json()
    project = build_actor_projection(MapRailsDiagnosticProjection())
    actual = project(turn)
    assert actual.prompt_version == "browsergym-map-rails-diagnostic-ax-v1"
    assert actual.model_dump_json() == project(turn).model_dump_json()
    rendered = tokenizer.apply_chat_template(
        [m.model_dump() for m in actual.messages],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    tokens = tokenizer(
        rendered, truncation=False, add_special_tokens=True, return_attention_mask=False
    )["input_ids"]
    assert type(rendered) is str and type(tokens) is list
    assert tokens and all(type(token) is int and token >= 0 for token in tokens)
    assert len(tokens) <= data["parameters"]["max_input_tokens"]
    assert len(tokens) + data["parameters"]["max_new_tokens"] <= data["context_window"]
    assert turn.observation.model_dump_json() == original_bytes
    assert "# Goal\n" + turn.task.goal in actual.messages[1].content
    assert "AX scope:" in actual.messages[1].content
    destination = (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / "map-actor-view-budget-facts.json"
    )
    destination.write_text(
        json.dumps(
            dict(
                original_job=4857567,
                original_prompt_tokens=37839,
                derived_prompt_tokens=len(tokens),
                max_input_tokens=data["parameters"]["max_input_tokens"],
                reserved_output=data["parameters"]["max_new_tokens"],
                context_window=data["context_window"],
                original_prompt_sha256=hashlib.sha256(
                    original.model_dump_json().encode()
                ).hexdigest(),
                derived_prompt_sha256=hashlib.sha256(
                    actual.model_dump_json().encode()
                ).hexdigest(),
                complete_original_observation_unchanged=True,
                source_or_model_inference_or_paid_calls=0,
            ),
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("change", ["title", "url", "foreign", "heading", "root"])
def test_nonmatching_diagnostic_page_keeps_full_baseline_scope(change: str) -> None:
    turn, _ = original_turn()
    observed = turn.observation.record
    tabs = list(observed.tabs)
    tab = tabs[0]
    text = turn.observation.text
    assert text is not None
    if change == "title":
        tabs[0] = tab.model_copy(update={"title": "Map"})
    elif change == "url":
        tabs[0] = tab.model_copy(update={"url": tab.url + "?other=1"})
    elif change == "foreign":
        tabs[0] = tab.model_copy(update={"url": "http://other:12345/map"})
    elif change == "heading":
        text = text.replace("heading 'Routes'", "heading 'Other'")
    else:
        text = text.replace("RootWebArea", "OtherWebArea", 1)
    observed = observed.model_copy(update={"tabs": tuple(tabs), "text": text})
    altered = ActorPublicTurn.model_validate(
        {
            **turn.model_dump(),
            "observation": ResolvedObservation(record=observed, text=text),
        }
    )
    assert build_actor_projection(MapRailsDiagnosticProjection())(
        altered
    ) == prepare_actor(altered)


def test_disabled_projection_is_exact_baseline_even_on_original_oversized_page() -> (
    None
):
    turn, original = original_turn()
    assert build_actor_projection(FullAxProjection())(turn) == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_task_id", "other"),
        ("task_id", "derived-other"),
        ("site", "reddit"),
        ("family", "navigation_page_identity"),
        ("split", "dev"),
        ("contract_version", 2),
    ],
)
def test_explicit_selected_view_refuses_other_task_scope(
    field: str, value: Any
) -> None:
    turn, _ = original_turn()
    identity = turn.task.identity.model_copy(update={field: value})
    public = turn.task.model_copy(update={"identity": identity})
    observed = turn.observation.record.model_copy(update={"task": identity})
    altered = ActorPublicTurn.model_validate(
        {
            **turn.model_dump(),
            "task": public,
            "observation": ResolvedObservation(
                record=observed, text=turn.observation.text
            ),
        }
    )
    with pytest.raises(OwnershipConflict):
        build_actor_projection(MapRailsDiagnosticProjection())(altered)


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        [],
        "",
        False,
        1,
        {"schema_version": "unknown/1"},
        {
            "schema_version": "actor-map-rails-diagnostic-projection/1",
            "contract_version": True,
        },
        {"schema_version": "actor-map-rails-diagnostic-projection/1", "ignored": True},
    ],
)
def test_projection_selection_rejects_illegal_type_missing_or_unknown_fields(
    value: Any,
) -> None:
    with pytest.raises(ValueError):
        actor_projection_configuration(value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        [],
        {},
        False,
        1,
        " root",
        "\t  [1] button 'mixed'",
        "[1] button 'x'\n\t[1] button 'y'",
    ],
)
def test_diagnostic_AX_rejects_empty_wrong_type_or_ambiguous_structure(
    value: Any,
) -> None:
    with pytest.raises(ValueError):
        diagnostic_ax_view(cast(str, value))


def test_only_duplicate_unaddressable_labels_and_empty_structural_IDs_removed() -> None:
    original = "[1] table ''\n\t[2] row ''\n\t\t[3] gridcell 'keep value'\n\t\t\t[4] paragraph ''\n\t\t\t\tStaticText 'keep value'\n\t[5] row '' selected=True\n\t\t[6] checkbox 'Toggle' checked=True\n\t\tStaticText 'independent text'\n"
    view = diagnostic_ax_view(original)
    assert view.duplicate_leaves == 1 and view.structural_ids == 2
    assert "  row ''\n    [3] gridcell 'keep value'\n      paragraph ''" in view.text
    assert "[5] row '' selected=True" in view.text
    assert "[6] checkbox 'Toggle' checked=True" in view.text
    assert "StaticText 'independent text'" in view.text
    assert diagnostic_ax_view(original) == view


def test_page_text_also_in_goal_does_not_change_goal_section() -> None:
    turn, _ = original_turn()
    text = turn.observation.text
    assert text is not None
    altered = ActorPublicTurn.model_validate(
        {**turn.model_dump(), "task": turn.task.model_copy(update={"goal": text})}
    )
    prompt = build_actor_projection(MapRailsDiagnosticProjection())(altered)
    assert prompt.messages[1].content.startswith(
        "# Goal\n" + text + "\n\n# Current URL\n"
    )
