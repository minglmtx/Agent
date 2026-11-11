"""Audit decoder for the old Gitaly child log; grants no wrapper stop approval.

The pinned production command runs gitaly-wrapper, whose normal exit is0 even
when the supervised Gitaly child logs exit1. Current require_stop refuses this
audit object as execution permission. Archived132 candidates retain its shape.
"""

import hashlib
import json
import re
from typing import Literal, Self, Any
from pydantic import Field, model_validator, field_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from .image import GITLAB_IMAGE_SHA


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate original Gitaly log key")
        result[key] = value
    return result


def _nonfinite(value: str) -> Any:
    raise ValueError("Nonfinite original Gitaly log value")


def check_gitaly_log(raw: str) -> None:
    lines = raw.splitlines()
    rows: list[dict[str, Any]] = []
    headers = 0
    for line in lines:
        if re.fullmatch(
            r'time="[0-9TZ:+.\-]+" level=info msg="Starting Gitaly, version 15\.7\.5"',
            line,
        ):
            headers += 1
        else:
            row = json.loads(line, object_pairs_hook=_pairs, parse_constant=_nonfinite)
            if type(row) is not dict:
                raise ValueError("Original Gitaly log must contain exact objects")
            rows.append(row)
    if headers != 1:
        raise ValueError("One exact original Gitaly 15.7.5 startup required")

    def one(message: str) -> tuple[int, dict[str, Any]]:
        found = [(i, r) for i, r in enumerate(rows) if r.get("msg") == message]
        if len(found) != 1:
            raise ValueError("One original Gitaly shutdown event required: " + message)
        return found[0]

    monitor_i, monitor = one("monitoring process")
    shutdown_i, shutdown = one("Gitaly shutdown")
    wait_i, waited = one("waiting for supervised command")
    finish_i, finish = one("wrapper for process shutting down")
    pid, child = monitor.get("pid"), monitor.get("process")
    if (
        type(pid) is not int
        or type(child) is not int
        or pid <= 0
        or child <= 0
        or pid == child
    ):
        raise ValueError("Original native Gitaly wrapper/child identities required")
    forwarded = [
        (i, r)
        for i, r in enumerate(rows)
        if r.get("msg") == "forwarding signal" and r.get("signal") == 15
    ]
    if len(forwarded) != 1:
        raise ValueError("One original Gitaly TERM forwarding required")
    term_i, term = forwarded[0]
    if not monitor_i < term_i < shutdown_i < wait_i < finish_i or (
        shutdown.get("error") != 'received signal "terminated"'
        or shutdown.get("level") != "error"
        or waited.get("error") != "exit status 1"
        or (waited.get("pid"), waited.get("wrapper")) != (pid, pid)
        or monitor.get("wrapper") != pid
        or any((r.get("pid"), r.get("process")) != (pid, child) for r in (term, finish))
        or any(
            r.get("signal") not in (15, 17)
            or (r.get("pid"), r.get("process"), r.get("wrapper")) != (pid, child, pid)
            for r in rows
            if r.get("msg") == "forwarding signal"
        )
    ):
        raise ValueError("Gitaly exit1 is not the exact original controlled TERM ABI")


class GitalyTermExit(Contract):
    schema_version: Literal["gitlab-gitaly-term-exit/1"] = "gitlab-gitaly-term-exit/1"
    original: NativeNamespaceIdentity
    image_sha256: Sha256
    log_bytes: int = Field(gt=0, le=65536)
    log_sha256: Sha256
    log: str = Field(min_length=1, max_length=65536)
    returncode: Literal[1] = 1

    @field_validator("returncode", mode="before")
    @classmethod
    def exact_returncode(cls, value: object) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("Original native returncode must be exact integer1")
        return value

    @model_validator(mode="after")
    def exact_native_proof(self) -> Self:
        raw = self.log.encode("utf-8")
        if (
            self.original.service != "gitaly"
            or self.image_sha256 != GITLAB_IMAGE_SHA
            or (len(raw), hashlib.sha256(raw).hexdigest())
            != (self.log_bytes, self.log_sha256)
        ):
            raise ValueError(
                "Fixed original Gitaly identity and complete log bytes required"
            )
        check_gitaly_log(self.log)
        return self
