"""Original normalized-goal stratified subset algorithm; no I/O or new split seed."""

import hashlib
import json
import unicodedata
from collections import defaultdict
from typing import Any
from lab_generate_skill.domain.dataset import TrainingExample


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def normalize_goal(goal: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", goal).casefold().split())


def group_key(row: dict[str, Any]) -> str:
    return normalize_goal(row["task"])


def split_groups(
    rows: list[dict[str, Any]], ratio: float = 0.05, seed: int = 42
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not 0 < ratio < 1:
        raise ValueError("dev ratio must be between 0 and 1")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    task_goals: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        groups[group_key(r)].append(r)
        task_goals[r["task_id"]].add(group_key(r))
    if any(len(g) > 1 for g in task_goals.values()):
        raise ValueError("Task ID spans different normalized goals")
    strata: dict[tuple[str, ...], list[tuple[str, list[dict[str, Any]]]]] = defaultdict(
        list
    )
    for goal, members in groups.items():
        strata[tuple(sorted({r["domain"] for r in members}))].append((goal, members))
    dev: set[str] = set()
    for domain, items in sorted(strata.items()):
        ordered = sorted(items, key=lambda x: fingerprint([seed, domain, x[0]]))
        if len(ordered) < 2:
            continue
        total = sum(len(v) for _, v in ordered)
        target = max(1, round(total * ratio))
        parents: dict[int, tuple[int, int] | None] = {0: None}
        for i, (_, records) in enumerate(ordered):
            for previous in sorted(tuple(parents), reverse=True):
                parents.setdefault(previous + len(records), (previous, i))
        choice = min(
            (n for n in parents if 0 < n < total), key=lambda n: (abs(n - target), n)
        )
        while choice:
            parent = parents[choice]
            assert parent is not None
            previous, i = parent
            dev.add(ordered[i][0])
            choice = previous
    train = [r for r in rows if group_key(r) not in dev]
    valid = [r for r in rows if group_key(r) in dev]
    if not train or not valid:
        raise ValueError("Not enough goal groups to create train and dev")
    return train, valid


def partition_examples(
    examples: tuple[TrainingExample, ...], ratio: float, seed: int
) -> dict[str, str]:
    known: dict[str, str] = {}
    rows = []
    for e in examples:
        goal = normalize_goal(e.group_goal)
        if known.setdefault(e.goal_group_id, goal) != goal:
            raise ValueError(
                "Frozen goal group has incompatible normalized member goals"
            )
        rows.append(
            {
                "id": e.example_id,
                "task_id": e.task.task_id,
                "domain": e.task.site,
                "task": e.group_goal,
            }
        )
    try:
        train, valid = split_groups(rows, ratio, seed)
    except ValueError as error:
        if str(error) != "Not enough goal groups to create train and dev":
            raise
        return {e.example_id: "candidate" for e in examples}
    return {
        **{r["id"]: "train" for r in train},
        **{r["id"]: "validation" for r in valid},
    }
