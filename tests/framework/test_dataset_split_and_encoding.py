"""Original split semantics and supervised prefix/mask boundaries; no models."""

from importlib import import_module
from typing import Any
import pytest
from lab_generate_skill.policies.dataset_split import normalize_goal, split_groups
from lab_generate_skill.adapters.training.supervised_encoding import (
    encode_supervised_record,
    token_ids,
)
from export_targets_fixtures import UnitChatTokenizer


def rows() -> list[dict[str, Any]]:
    return [
        dict(id=str(i), task_id="task-" + str(i), domain=site, task=goal)
        for i, (site, goal) in enumerate(
            [
                ("map", "Find A"),
                ("map", " find  a "),
                ("map", "Find B"),
                ("map", "Find C"),
                ("gitlab", "Find A"),
                ("gitlab", "Find D"),
                ("gitlab", "Find E"),
                ("shopping", "Only singleton stratum"),
            ]
        )
    ]


def test_normalized_goal_group_cohesion_order_and_strata_are_preserved() -> None:
    data = rows()
    train, valid = split_groups(data)
    assert train and valid and train + valid != []
    assert {r["id"] for r in train}.isdisjoint({r["id"] for r in valid})
    assert len(train) + len(valid) == len(data)
    assert {normalize_goal(r["task"]) for r in train}.isdisjoint(
        {normalize_goal(r["task"]) for r in valid}
    )
    assert [r for r in data if r in train] == train
    assert [r for r in data if r in valid] == valid
    assert next(r for r in data if r["domain"] == "shopping") in train
    assert split_groups(list(reversed(data)))[1] == list(reversed(valid))
    assert normalize_goal(" Ａ\t B  ") == normalize_goal("a b")


@pytest.mark.parametrize(
    "data", [[], [dict(task_id="one", domain="map", task="Only one")]]
)
def test_no_split_is_invented_for_empty_or_single_goal(
    data: list[dict[str, Any]],
) -> None:
    with pytest.raises(ValueError, match="Not enough goal groups"):
        split_groups(data)


def test_same_original_task_id_cannot_span_different_goals() -> None:
    data = rows()
    data[2]["task_id"] = data[0]["task_id"]
    with pytest.raises(ValueError, match="Task ID spans"):
        split_groups(data)


@pytest.mark.parametrize("ratio", [0.0, 1.0, -1.0, float("nan")])
def test_original_split_rejects_out_of_range_ratio(ratio: float) -> None:
    with pytest.raises(ValueError, match="dev ratio"):
        split_groups(rows(), ratio)


def record() -> dict[str, Any]:
    return dict(
        id="unit-row",
        messages=[
            dict(role="system", content="rules"),
            dict(role="user", content="task"),
            dict(role="assistant", content="complete skill"),
        ],
    )


def test_supervised_encoder_exact_window_and_loss_mask() -> None:
    tokenizer = UnitChatTokenizer()
    encoded = encode_supervised_record(tokenizer, record(), max_seq_length=4096)
    n = len(encoded["input_ids"])
    for limit in (n, n + 1):
        assert (
            encode_supervised_record(tokenizer, record(), max_seq_length=limit)
            == encoded
        )
    with pytest.raises(ValueError, match="above"):
        encode_supervised_record(tokenizer, record(), max_seq_length=n - 1)
    prompt = encoded["prompt_tokens"]
    assert encoded["labels"][:prompt] == [-100] * prompt
    assert encoded["labels"][prompt:] == encoded["input_ids"][prompt:]
    assert encoded["assistant_tokens"] == n - prompt > 0
    assert token_ids({"input_ids": [[1, 2]]}) == [1, 2]
    with pytest.raises(ValueError, match="unbatched"):
        token_ids([[1], [2]])


class BrokenTemplate:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def apply_chat_template(
        self,
        messages: object,
        *,
        tokenize: bool,
        add_generation_prompt: bool,
        enable_thinking: bool,
    ) -> list[int]:
        if add_generation_prompt:
            return [1, 2]
        return [2, 1, 3] if self.mode == "wrong-prefix" else [1, 2]


@pytest.mark.parametrize(
    "mode,match", [("wrong-prefix", "not a prefix"), ("empty-output", "no supervised")]
)
def test_inconsistent_template_or_missing_output_is_not_silently_encoded(
    mode: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        encode_supervised_record(BrokenTemplate(mode), record(), max_seq_length=4096)


def test_original_public_helpers_alias_the_single_shared_implementation() -> None:
    old_encoder = import_module("lab_generate_skill.sft_train")
    old_split = import_module("lab_generate_skill.generator_sft")
    assert old_encoder.encode_supervised_record is encode_supervised_record
    assert old_encoder.token_ids is token_ids
    assert old_split.split_groups is split_groups
    assert old_split.normalize_goal is normalize_goal
