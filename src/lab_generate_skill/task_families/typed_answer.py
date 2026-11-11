"""Original typed JSON answer parser; duplicate keys are never accepted."""

import json


def parse_answer(answer: str | None) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_answer_key")
            result[key] = value
        return result

    if type(answer) is not str:
        raise TypeError("answer_not_text")
    value = json.loads(answer, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("answer_not_object")
    return value
