"""Original SFT template/prefix/masking encoder, shared by all consumers."""

from typing import Any, Mapping


def token_ids(value: Any) -> list[int]:
    if isinstance(value, Mapping):
        value = value["input_ids"]
    if value and isinstance(value[0], list):
        if len(value) != 1:
            raise ValueError("expected one unbatched token sequence")
        value = value[0]
    return list(value)


def encode_supervised_record(
    tokenizer: Any, record: dict[str, Any], *, max_seq_length: int
) -> dict[str, Any]:
    messages = record["messages"]
    roles = [message["role"] for message in messages]
    if roles not in (["system", "user", "assistant"], ["user", "assistant"]):
        raise ValueError(f"unexpected roles for {record['id']}")
    prompt_ids = token_ids(
        tokenizer.apply_chat_template(
            messages[:-1],
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    )
    full_ids = token_ids(
        tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=False,
            enable_thinking=False,
        )
    )
    if full_ids[: len(prompt_ids)] != prompt_ids:
        raise ValueError(
            f"prompt is not a prefix of full conversation for {record['id']}"
        )
    if len(full_ids) > max_seq_length:
        raise ValueError(
            f"sample {record['id']} has {len(full_ids)} tokens, above {max_seq_length}"
        )
    if len(full_ids) == len(prompt_ids):
        raise ValueError(f"sample {record['id']} has no supervised assistant tokens")
    return {
        "id": str(record["id"]),
        "input_ids": full_ids,
        "labels": [-100] * len(prompt_ids) + full_ids[len(prompt_ids) :],
        "prompt_tokens": len(prompt_ids),
        "assistant_tokens": len(full_ids) - len(prompt_ids),
    }
