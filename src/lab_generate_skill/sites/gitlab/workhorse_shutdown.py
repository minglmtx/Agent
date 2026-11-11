"""Pinned Workhorse exit1 with nil shutdown, preserving complete bounded bytes."""

import base64
import gzip
import hashlib
import io
import shlex
import zlib
from typing import Literal, Self
from pydantic import Field, model_validator, field_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from .image import GITLAB_IMAGE_SHA

MAX_LOG_BYTES = 8 * 1024 * 1024
MAX_COMPRESSED_BYTES = 48 * 1024


def check_workhorse_log(raw: bytes) -> None:
    rows: list[tuple[int, dict[str, str]]] = []
    lines = raw.decode("utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("time="):
            continue  # Preserve unstructured HTTP access lines in the full bytes.
        fields: dict[str, str] = {}
        for token in shlex.split(line):
            key, separator, value = token.partition("=")
            if not separator or key in fields:
                raise ValueError("Invalid or duplicate original Workhorse log field")
            fields[key] = value
        rows.append((index, fields))

    def one(message: str) -> tuple[int, dict[str, str]]:
        found = [(i, row) for i, row in rows if row.get("msg") == message]
        if len(found) != 1:
            raise ValueError(
                "One original Workhorse shutdown event required: " + message
            )
        return found[0]

    start_i, start = one("Starting")
    term_i, term = one("shutdown initiated")
    done_i, done = one("shutting down")
    if (
        not start_i < term_i < done_i
        or done_i != len(lines) - 1
        or (
            start.get("version") != "v15.7.5"
            or term.get("signal") != "terminated"
            or term.get("shutdown_timeout_s") != "10"
            or term.get("level") != "info"
            or done.get("level") != "fatal"
            or done.get("error") != "<nil>"
        )
    ):
        raise ValueError("Workhorse exit1 lacks exact original10s TERM/nil completion")


class WorkhorseTermExit(Contract):
    schema_version: Literal["gitlab-workhorse-term-exit/1"] = (
        "gitlab-workhorse-term-exit/1"
    )
    original: NativeNamespaceIdentity
    image_sha256: Sha256
    log_bytes: int = Field(gt=0, le=MAX_LOG_BYTES)
    log_sha256: Sha256
    log_gzip_base64: str = Field(min_length=1, max_length=65536)
    returncode: Literal[1] = 1

    @field_validator("returncode", mode="before")
    @classmethod
    def exact_returncode(cls, value: object) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("Original Workhorse returncode must be exact integer1")
        return value

    def raw_log(self) -> bytes:
        try:
            compressed = base64.b64decode(self.log_gzip_base64, validate=True)
            if (
                len(compressed) > MAX_COMPRESSED_BYTES
                or base64.b64encode(compressed).decode() != self.log_gzip_base64
            ):
                raise ValueError("Bounded canonical compressed Workhorse log required")
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                raw = stream.read(MAX_LOG_BYTES + 1)
        except (OSError, EOFError, ValueError, zlib.error) as error:
            raise ValueError("Invalid complete compressed Workhorse log") from error
        if len(raw) > MAX_LOG_BYTES or (len(raw), hashlib.sha256(raw).hexdigest()) != (
            self.log_bytes,
            self.log_sha256,
        ):
            raise ValueError("Complete original Workhorse log bytes changed")
        return raw

    @model_validator(mode="after")
    def original_nil_exit(self) -> Self:
        if (
            self.original.service not in ("workhorse", "workhorse-internal")
            or self.image_sha256 != GITLAB_IMAGE_SHA
        ):
            raise ValueError("Fixed original native Workhorse implementation required")
        check_workhorse_log(self.raw_log())
        return self

    @classmethod
    def from_raw(
        cls, original: NativeNamespaceIdentity, image_sha256: str, raw: bytes
    ) -> Self:
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_LOG_BYTES:
            raise ValueError("Complete bounded original Workhorse bytes required")
        return cls(
            original=original,
            image_sha256=image_sha256,
            log_bytes=len(raw),
            log_sha256=hashlib.sha256(raw).hexdigest(),
            log_gzip_base64=base64.b64encode(gzip.compress(raw, mtime=0)).decode(),
        )
