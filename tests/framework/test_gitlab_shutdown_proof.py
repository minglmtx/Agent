"""A child exit log is not wrapper status; reuse the actual607 native receipt."""

from pathlib import Path
import hashlib
import json
import os
import pytest
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.sites.gitlab.shutdown_contract import GitalyTermExit
from lab_generate_skill.sites.gitlab.shutdown_log import read_gitaly_term_exit
from lab_generate_skill.sites.gitlab.image import GITLAB_IMAGE_SHA
from lab_generate_skill.sites.gitlab.services import require_stop
from lab_generate_skill.sites.gitlab.snapshot import GitlabSnapshots
from lab_generate_skill.sites.gitlab.tasks.ssh_key_recovery import SshKeyRestored
from gitlab_native_fixtures import spec, Commands
from test_gitlab_snapshots import original_group
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard

LOG = Path(__file__).parent / "fixtures/gitlab-4790081-gitaly-stop.log"
ACTUAL = Path(__file__).parent / "fixtures/gitlab-4790607-ssh-restored.json"


def original(generation: int = 0) -> NativeServiceQuiescence:
    return original_group(generation).quiesce(guard())


def proof(
    stopped: NativeServiceQuiescence, *, text: str | None = None
) -> GitalyTermExit:
    raw = LOG.read_bytes() if text is None else text.encode()
    return GitalyTermExit(
        original=next(
            n.original for n in stopped.namespaces if n.original.service == "gitaly"
        ),
        image_sha256=GITLAB_IMAGE_SHA,
        log_bytes=len(raw),
        log_sha256=hashlib.sha256(raw).hexdigest(),
        log=raw.decode(),
    )


def test_actual_original_snapshot_restore_receipt_keeps_gitaly_wrapper_zero() -> None:
    restored = SshKeyRestored.model_validate_json(ACTUAL.read_bytes())
    for stopped, terms in (
        (
            restored.snapshot.state.original_stop,
            restored.snapshot.state.workhorse_terms,
        ),
        (restored.stopped, restored.workhorse_terms),
    ):
        assert next(m for m in stopped.masters if m.service == "gitaly").returncode == 0
        assert len(terms) == 2 and all(t.returncode == 1 for t in terms)
        require_stop(
            stopped, tuple(n.original for n in stopped.namespaces), None, terms
        )
    assert restored.gitaly_term is None and restored.snapshot.state.gitaly_term is None
    assert (
        restored.inventory.bytes == 31162022947
        and restored.inventory == restored.snapshot.state.inventory
    )


@pytest.mark.parametrize("code", [1, -9, -15, 143])
def test_child_exit1_log_never_authorizes_nonzero_gitaly_wrapper(
    node_path: Path, code: int
) -> None:
    stopped = original()
    value = stopped.model_dump(mode="json")
    for row in value["masters"]:
        if row["service"] == "gitaly":
            row["returncode"] = code
    for row in value["namespaces"]:
        if row["original"]["service"] == "gitaly":
            row["launcher_returncode"] = code
    bad = NativeServiceQuiescence.model_validate_json(json.dumps(value))
    pins = tuple(n.original for n in bad.namespaces)
    commands = Commands(node_path)
    snapshots = GitlabSnapshots(spec(node_path), commands)
    with pytest.raises(ValueError):
        snapshots.save(bad, pins, guard())
    assert not snapshots.saving and not commands.calls
    with pytest.raises(ValueError, match="child exit log"):
        require_stop(bad, pins, proof(bad))
    with pytest.raises(ValueError, match="child exit log"):
        require_stop(
            stopped, tuple(n.original for n in stopped.namespaces), proof(stopped)
        )


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "header",
        "signal",
        "pid",
        "cause",
        "duplicate",
        "truncated",
        "unknown_line",
        "json_duplicate",
        "nonfinite",
    ],
)
def test_old_child_log_audit_decoder_refuses_corrupt_or_ambiguous_bytes(
    case: str,
) -> None:
    text = LOG.read_text()
    if case == "empty":
        text = ""
    elif case == "header":
        text = text.replace("version 15.7.5", "version 15.7.6")
    elif case == "signal":
        text = text.replace('"signal":15', '"signal":9')
    elif case == "pid":
        text = text.replace('"process":28', '"process":29', 1)
    elif case == "cause":
        text = text.replace('received signal \\"terminated\\"', "internal fatal error")
    elif case == "duplicate":
        text += (
            next(
                line for line in text.splitlines() if '"msg":"Gitaly shutdown"' in line
            )
            + "\n"
        )
    elif case == "truncated":
        text = "\n".join(text.splitlines()[:-1]) + "\n"
    elif case == "unknown_line":
        text += "unrecognized failure\n"
    elif case == "json_duplicate":
        text = text.replace('{"level":"info"', '{"level":"info","level":"info"', 1)
    elif case == "nonfinite":
        text = text.replace('{"level":"info"', '{"unexpected":NaN,"level":"info"', 1)
    assert text != LOG.read_text()
    with pytest.raises(ValueError):
        proof(original(), text=text)


@pytest.mark.parametrize(
    "case", ["normal", "repeat", "link", "hardlink", "large", "cancel"]
)
def test_audit_log_read_has_no_mutation_and_grants_no_stop_permission(
    node_path: Path, case: str
) -> None:
    stopped = original()
    root = node_path / "generation-1"
    root.mkdir()
    path = root / "gitaly.log"
    path.write_bytes(LOG.read_bytes())
    if case == "link":
        path.unlink()
        path.symlink_to(LOG)
    elif case == "hardlink":
        os.link(path, root / "other")
    elif case == "large":
        path.write_bytes(b"x" * 65537)
    selected = next(
        n.original for n in stopped.namespaces if n.original.service == "gitaly"
    )
    if case in ("link", "hardlink", "large", "cancel"):
        with pytest.raises((ValueError, RuntimeError)):
            read_gitaly_term_exit(
                root, selected, GITLAB_IMAGE_SHA, guard(0 if case == "cancel" else 5)
            )
    else:
        audit = read_gitaly_term_exit(root, selected, GITLAB_IMAGE_SHA, guard())
        assert audit == proof(stopped) and path.read_bytes() == LOG.read_bytes()
        if case == "repeat":
            assert (
                read_gitaly_term_exit(root, selected, GITLAB_IMAGE_SHA, guard())
                == audit
            )
        with pytest.raises(ValueError, match="child exit log"):
            require_stop(stopped, tuple(n.original for n in stopped.namespaces), audit)
