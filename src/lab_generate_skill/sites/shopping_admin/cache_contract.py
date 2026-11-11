"""Explicit local cache invalidation facts, not search or whole-site recovery."""

from typing import Literal
from pydantic import field_validator
from lab_generate_skill.domain.validation import Contract
from .service_contract import AdminServiceSpec


class AdminCacheReset(Contract):
    schema_version: Literal["admin-cache-reset/1"] = "admin-cache-reset/1"
    service: AdminServiceSpec
    application_cache_command_succeeded: Literal[True]
    redis_all_databases_empty: Literal[True]

    @field_validator(
        "application_cache_command_succeeded",
        "redis_all_databases_empty",
        mode="before",
    )
    @classmethod
    def actual_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Successful cache facts require exact boolean true")
        return value
