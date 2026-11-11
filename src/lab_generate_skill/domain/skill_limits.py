"""Pure compact-soft-v2 hard limits, preserved from the frozen legacy policy."""

import re

_LINE = re.compile(r"(?m)^[ \t]*(\d+)[.)](?:[ \t]+|(?=\n|$))")
_INLINE = re.compile(r"(?<!\S)(\d+)[.)](?:[ \t]+|(?=\n|$))")
_WORD = re.compile(r"[A-Za-z0-9]+(?:['’_-][A-Za-z0-9]+)*")


def numbered_steps(text: str) -> list[re.Match[str]]:
    first = _LINE.match(text)
    return list(
        (_INLINE if first and int(first.group(1)) == 1 else _LINE).finditer(text)
    )


def word_count(text: str) -> int:
    for step in reversed(numbered_steps(text)):
        text = text[: step.start()] + text[step.end() :]
    return len(_WORD.findall(text))


def validate_skill(title: str, principle: str, when_to_apply: str) -> None:
    counts = [word_count(value) for value in (title, principle, when_to_apply)]
    if (
        any(count > limit for count, limit in zip(counts, (12, 200, 70)))
        or sum(counts) > 220
    ):
        raise ValueError("CompactSkill hard word budget exceeded")
    if re.search(r"(?m)^[ \t]*[-*•][ \t]+", principle):
        raise ValueError("Procedures use consecutive numbered steps")
    steps = numbered_steps(principle)
    if steps:
        if (
            len(steps) > 6
            or principle[: steps[0].start()].strip()
            or [int(step.group(1)) for step in steps] != list(range(1, len(steps) + 1))
        ):
            raise ValueError("Invalid procedure numbering or step count")
        for index, step in enumerate(steps):
            end = steps[index + 1].start() if index + 1 < len(steps) else len(principle)
            if not principle[step.end() : end].strip():
                raise ValueError("Procedure steps cannot be empty")
