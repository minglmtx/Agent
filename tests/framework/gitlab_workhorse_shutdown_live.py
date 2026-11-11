"""Small pinned Workhorse shutdown ABI; no GitLab seed, database or Actor."""

from pathlib import Path
from typing import Literal, Any
import json
import os
import shutil
import socket
import stat
import subprocess
import tempfile
import hashlib
import pytest
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.sites.gitlab.image import GITLAB_IMAGE_SHA
from lab_generate_skill.sites.gitlab.workhorse_shutdown import WorkhorseTermExit
from test_slurm_commands import guard

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
IMAGE = W / "assets/webarena/gitlab" / GITLAB_IMAGE_SHA / "gitlab.sif"
BASE = (
    "/usr/bin/apptainer",
    "exec",
    "--cleanenv",
    "--containall",
    "--no-home",
    "--no-mount",
    "bind-paths,hostfs,cwd",
    "--pwd",
    "/",
)


def command(root: Path, seconds: Literal["0s", "10s"]) -> tuple[str, ...]:
    if (
        seconds not in ("0s", "10s")
        or not root.is_absolute()
        or not root.is_relative_to("/tmp")
        or root == Path("/tmp")
        or any(c in str(root) for c in (":", ",", "\n", "\0"))
    ):
        raise ValueError("Fixed private native shutdown fixture required")
    return BASE + (
        "--bind",
        str(root) + ":/test",
        str(IMAGE),
        "/opt/gitlab/embedded/bin/gitlab-workhorse",
        "-listenNetwork",
        "unix",
        "-listenAddr",
        "/test/workhorse.socket",
        "-authBackend",
        "http://127.0.0.1:1",
        "-documentRoot",
        "/opt/gitlab/embedded/service/gitlab-rails/public",
        "-secretPath",
        "/opt/gitlab/embedded/service/gitlab-rails/.gitlab_workhorse_secret",
        "-config",
        "/test/config.toml",
    )


def test_fixture_is_inert_and_refuses_foreign_paths_or_shutdown_modes(
    tmp_path: Path,
) -> None:
    assert "gitlab-workhorse" in " ".join(
        command(Path("/tmp/unique-stop-fixture"), "10s")
    )
    bad: Any = "60s"
    with pytest.raises(ValueError):
        command(Path("/tmp/fresh"), bad)
    for path in (Path("relative"), Path("/tmp"), Path("/tmp/fresh:alias")):
        with pytest.raises(ValueError):
            command(path, "10s")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("seconds,expected", [("0s", 1), ("10s", 1)])
def test_actual_original_workhorse_timeout_and_complete_namespace_exit(
    seconds: Any, expected: int
) -> None:
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / (
        "workhorse-shutdown-" + seconds
    )
    output.mkdir(mode=0o700)
    # Read only the pinned image's small original config. No full seed/copy.
    read = subprocess.run(
        BASE + (str(IMAGE), "/bin/cat", "/var/opt/gitlab/gitlab-workhorse/config.toml"),
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert read.returncode == 0 and not read.stderr and 0 < len(read.stdout) < 16384
    assert b"shutdown_timeout" not in read.stdout
    (output / "original-config.sha256").write_text(
        hashlib.sha256(read.stdout).hexdigest() + "\n"
    )
    root = Path(tempfile.mkdtemp(prefix="lab-gitlab-workhorse-stop-", dir="/tmp"))
    logs = root / "logs"
    logs.mkdir(mode=0o700)
    config = root / "config.toml"
    config.write_text('shutdown_timeout = "' + seconds + '"\n')
    config.chmod(0o600)
    services = LocalNativeServices(logs)
    primary: BaseException | None = None
    cleanup: list[BaseException] = []
    facts: dict[str, Any] = dict(
        passed=False,
        private_root=str(root),
        original_seconds=seconds,
        actual_gitlab_database_started=False,
        full_native_seed_copied=False,
        actor_calls=0,
        paid_calls=0,
    )
    stopped = None
    try:
        control = guard(40)
        services.start("workhorse", command(root, seconds), control)
        endpoint = root / "workhorse.socket"
        while not endpoint.exists():
            services.require_running()
            control.wait(0.05)
        assert stat.S_ISSOCK(endpoint.lstat().st_mode)
        pin = services.pin_namespace("workhorse", control)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(endpoint))
            # Keep a partial request open so zero-deadline shutdown cannot
            # race with an already-idle server. No backend is available here.
            client.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n")
            control.wait(0.2)
            stopped = services.quiesce(control)
        facts["original_pin"] = pin.model_dump(mode="json")
        facts["stopped"] = stopped.model_dump(mode="json")
        raw = (logs / "workhorse.log").read_bytes()
        assert len(raw) <= 256 * 1024
        (output / "workhorse.log").write_bytes(raw)
        if seconds == "10s":
            proof = WorkhorseTermExit.from_raw(pin, GITLAB_IMAGE_SHA, raw)
            assert proof.raw_log() == raw
            facts["native_nil_completion_proof"] = proof.model_dump(mode="json")
        assert (
            stopped.masters[0].returncode == expected
            and not stopped.masters[0].kill_requested
        )
        assert (
            stopped.namespaces[0].original == pin
            and stopped.namespaces[0].init_exit_observed
        )
        assert (b"context deadline exceeded" in raw) == (seconds == "0s")
        facts["passed"] = True
    except BaseException as error:
        primary = error
    finally:
        try:
            services.stop(guard(20))
        except BaseException as error:
            cleanup.append(error)
        if (logs / "workhorse.log").is_file() and not (
            output / "workhorse.log"
        ).exists():
            shutil.copyfile(logs / "workhorse.log", output / "workhorse.log")
        facts["primary"] = (
            None if primary is None else describe_error(primary).model_dump(mode="json")
        )
        facts["cleanup_errors"] = [
            describe_error(e).model_dump(mode="json") for e in cleanup
        ]
        safe = (
            stopped is not None
            and not cleanup
            and all(n.init_exit_observed for n in stopped.namespaces)
        )
        if safe:
            shutil.rmtree(root)
        facts["private_root_removed"] = safe and not root.exists()
        (output / "result.json").write_text(json.dumps(facts, indent=2) + "\n")
    if primary is not None:
        if cleanup:
            raise BaseExceptionGroup(
                "Original Workhorse fixture failure and cleanup", [primary, *cleanup]
            )
        raise primary
    if cleanup:
        raise BaseExceptionGroup("Workhorse fixture cleanup", cleanup)
