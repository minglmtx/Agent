"""Exact native nil exit, full log compression bounds and original stop joins."""

from pathlib import Path
import base64
import gzip
import hashlib
import json
import pytest
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.sites.gitlab.workhorse_shutdown import (
    WorkhorseTermExit,
    MAX_LOG_BYTES,
)
from lab_generate_skill.sites.gitlab.shutdown_log import read_workhorse_term_exit
from lab_generate_skill.sites.gitlab.services import require_stop
from lab_generate_skill.sites.gitlab.image import GITLAB_IMAGE_SHA
from test_gitlab_shutdown_proof import original
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard

LOG = Path(__file__).parent / "fixtures/gitlab-4790431-workhorse-10s.log"


def complete_stop(generation: int = 0) -> NativeServiceQuiescence:
    value = original(generation).model_dump(mode="json")
    for row in value["masters"]:
        if row["service"] in ("workhorse", "workhorse-internal"):
            row["returncode"] = 1
    for row in value["namespaces"]:
        if row["original"]["service"] in ("workhorse", "workhorse-internal"):
            row["launcher_returncode"] = 1
    return NativeServiceQuiescence.model_validate_json(json.dumps(value))


def completion(
    stopped: NativeServiceQuiescence, name: str = "workhorse", raw: bytes | None = None
) -> WorkhorseTermExit:
    pin = next(p.original for p in stopped.namespaces if p.original.service == name)
    return WorkhorseTermExit.from_raw(
        pin, GITLAB_IMAGE_SHA, LOG.read_bytes() if raw is None else raw
    )


def test_complete_bounded_original_logs_and_both_service_proofs_survive_readback(
    node_path: Path,
) -> None:
    stopped = complete_stop()
    pins = tuple(n.original for n in stopped.namespaces)
    with pytest.raises(ValueError, match="Workhorse"):
        require_stop(stopped, pins, None)
    both = tuple(
        completion(stopped, name) for name in ("workhorse-internal", "workhorse")
    )
    require_stop(stopped, pins, None, both)
    assert all(
        WorkhorseTermExit.model_validate_json(p.model_dump_json()) == p for p in both
    )
    root = node_path / "generation-1"
    root.mkdir()
    for p in both:
        (root / (p.original.service + ".log")).write_bytes(p.raw_log())
        assert (
            read_workhorse_term_exit(root, p.original, GITLAB_IMAGE_SHA, guard()) == p
        )
    raw = LOG.read_bytes()
    line = raw.index(b"\n") + 1
    larger = raw[:line] + b"127.0.0.1 controlled full access log\n" * 10000 + raw[line:]
    p = completion(stopped, raw=larger)
    assert (
        len(larger) > 256 * 1024
        and p.raw_log() == larger
        and len(p.model_dump_json()) < 65536
    )
    assert p.log_sha256 == hashlib.sha256(larger).hexdigest()


@pytest.mark.parametrize(
    "case",
    [
        "zero_timeout",
        "timeout",
        "signal",
        "version",
        "duplicate",
        "trailing",
        "duplicate_key",
        "bool_code",
        "hash",
        "image",
        "base64",
        "gzip",
        "truncated",
        "bomb",
        "large_raw",
    ],
)
def test_missing_ambiguous_corrupt_or_timed_out_exit_stays_rejected(case: str) -> None:
    stopped = complete_stop()
    raw = LOG.read_bytes()
    value = completion(stopped).model_dump()
    if case == "zero_timeout":
        raw = (LOG.parent / "gitlab-4790431-workhorse-0s.log").read_bytes()
    elif case == "timeout":
        raw = raw.replace(b"<nil>", b"context deadline exceeded")
    elif case == "signal":
        raw = raw.replace(b"signal=terminated", b"signal=killed")
    elif case == "version":
        raw = raw.replace(b"version=v15.7.5", b"version=v15.7.6")
    elif case == "duplicate":
        raw += raw.splitlines()[-1] + b"\n"
    elif case == "trailing":
        raw += b"unrecognized later failure\n"
    elif case == "duplicate_key":
        raw = raw.replace(
            b"shutdown_timeout_s=10", b"shutdown_timeout_s=10 shutdown_timeout_s=10"
        )
    elif case == "bool_code":
        value["returncode"] = True
    elif case == "hash":
        value["log_sha256"] = "0" * 64
    elif case == "image":
        value["image_sha256"] = "0" * 64
    elif case == "base64":
        value["log_gzip_base64"] = "invalid!"
    elif case == "gzip":
        value["log_gzip_base64"] = base64.b64encode(b"not gzip").decode()
    elif case == "truncated":
        value["log_gzip_base64"] = value["log_gzip_base64"][:-4]
    elif case == "bomb":
        value["log_gzip_base64"] = base64.b64encode(
            gzip.compress(b"x" * (MAX_LOG_BYTES + 1), mtime=0)
        ).decode()
    elif case == "large_raw":
        raw = b"x" * (MAX_LOG_BYTES + 1)
    with pytest.raises(ValueError):
        if case in (
            "zero_timeout",
            "timeout",
            "signal",
            "version",
            "duplicate",
            "trailing",
            "duplicate_key",
            "large_raw",
        ):
            completion(stopped, raw=raw)
        else:
            WorkhorseTermExit.model_validate(value)


@pytest.mark.parametrize("case", ["foreign", "duplicate", "missing"])
def test_namespace_and_complete_service_join_cannot_be_replaced(case: str) -> None:
    stopped = complete_stop()
    pins = tuple(n.original for n in stopped.namespaces)
    both = (completion(stopped, "workhorse-internal"), completion(stopped))
    selected = (
        (completion(complete_stop(1), "workhorse-internal"), both[1])
        if case == "foreign"
        else (both[0], both[0]) if case == "duplicate" else (both[0],)
    )
    with pytest.raises(ValueError):
        require_stop(stopped, pins, None, selected)
