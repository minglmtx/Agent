"""Versioned split membership and alias/goal lineage, with no file discovery.

The manifest describes the complete declared partition. Its publisher must prove
completeness and source identity; constructing these values is not qualification.
Normalization preserves the existing NFKC/casefold/whitespace exclusion rule.
"""

import unicodedata
from typing import Literal, Self

from pydantic import Field, model_validator

from .identity import TaskIdentity
from .validation import Contract, Identifier, NonEmptyText


def normalized_goal(text: str) -> str:
    if type(text) is not str or not text.strip():
        raise ValueError("Goal must be nonempty text")
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class SplitMember(Contract):
    identity: TaskIdentity
    goal_group_id: Identifier
    public_goal: NonEmptyText
    aliases: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def distinct_aliases(self) -> Self:
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError("Duplicate task aliases")
        return self

    @property
    def source_ids(self) -> frozenset[str]:
        return frozenset(
            (self.identity.source_task_id, self.identity.task_id, *self.aliases)
        )


class SplitManifest(Contract):
    schema_version: Literal["data-split/1"] = "data-split/1"
    partition_id: Identifier
    members: tuple[SplitMember, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def disjoint(self) -> Self:
        seen: set[str] = set()
        groups: dict[str, str] = {}
        for member in self.members:
            if seen.intersection(member.source_ids):
                raise ValueError("Task/source aliases identify multiple split members")
            seen.update(member.source_ids)
            previous = groups.setdefault(member.goal_group_id, member.identity.split)
            if previous != member.identity.split:
                raise ValueError("Goal group crosses data partitions")
        return self

    def member(self, identity: TaskIdentity) -> SplitMember:
        identity = TaskIdentity.model_validate(identity)
        for member in self.members:
            if member.identity == identity:
                return member
        raise ValueError("Task is absent from the exact frozen partition")
