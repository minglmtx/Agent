"""Exact original six service commands; fixed private mounts, no legacy runner."""

from typing import Literal
from .service_contract import GitlabServiceSpec

SERVICE_NAMES = (
    "postgres",
    "redis",
    "gitaly",
    "puma",
    "workhorse-internal",
    "workhorse",
)
RUBY = "/opt/gitlab/embedded/bin/ruby"


def container(
    spec: GitlabServiceSpec,
    *,
    seeded: bool = True,
    snapshot: Literal["none", "save", "read"] = "none",
) -> tuple[str, ...]:
    spec = GitlabServiceSpec.model_validate(spec)
    if type(seeded) is not bool or snapshot not in ("none", "save", "read"):
        raise ValueError("Explicit native GitLab mount mode required")
    args: tuple[str, ...] = (
        spec.apptainer,
        "exec",
        "--cleanenv",
        "--containall",
        "--no-home",
        "--no-mount",
        "bind-paths,hostfs,cwd",
        "--pwd",
        "/",
        "--bind",
        spec.files.state_root + ":/state",
        "--bind",
        spec.control_root + ":/control:ro",
    )
    if seeded:
        for path, target in (
            ("data", "/var/opt/gitlab"),
            ("log", "/var/log/gitlab"),
            ("optvar", "/opt/gitlab/var"),
            ("tmp", "/tmp"),
            ("var-tmp", "/var/tmp"),
        ):
            args += ("--bind", spec.files.state_root + "/" + path + ":" + target)
    if snapshot != "none":
        args += (
            "--bind",
            spec.snapshot_root + ":/snapshot" + (":ro" if snapshot == "read" else ""),
        )
    return args + (spec.files.image_path,)


def service_commands(spec: GitlabServiceSpec) -> dict[str, tuple[str, ...]]:
    spec = GitlabServiceSpec.model_validate(spec)
    base = container(spec)
    wrapper = ("/bin/bash", "/control/service.sh")
    workhorse = wrapper + (
        "gitlab-workhorse",
        "/opt/gitlab/embedded/bin/gitlab-workhorse",
    )
    backend = (
        "-authBackend",
        "http://localhost:8080",
        "-authSocket",
        "/var/opt/gitlab/gitlab-rails/sockets/gitlab.socket",
        "-documentRoot",
        "/opt/gitlab/embedded/service/gitlab-rails/public",
        "-secretPath",
        "/opt/gitlab/embedded/service/gitlab-rails/.gitlab_workhorse_secret",
        "-config",
        "/var/opt/gitlab/gitlab-workhorse/config.toml",
    )
    return {
        "postgres": base
        + (
            "/opt/gitlab/embedded/bin/postgres",
            "-D",
            "/var/opt/gitlab/postgresql/data",
            "-c",
            "listen_addresses=",
            "-c",
            "unix_socket_directories=/var/opt/gitlab/postgresql",
            "-c",
            "shared_buffers=256MB",
        ),
        "redis": base
        + (
            "/opt/gitlab/embedded/bin/redis-server",
            "/var/opt/gitlab/redis/redis.conf",
            "--daemonize",
            "no",
            "--supervised",
            "no",
            "--port",
            "0",
        ),
        "gitaly": base
        + wrapper
        + (
            "gitaly",
            "/opt/gitlab/embedded/bin/gitaly-wrapper",
            "/opt/gitlab/embedded/bin/gitaly",
            "/var/opt/gitlab/gitaly/config.toml",
        ),
        "puma": base
        + wrapper
        + (
            "gitlab-rails",
            "/opt/gitlab/embedded/bin/bundle",
            "exec",
            "puma",
            "-C",
            "/var/opt/gitlab/gitlab-rails/etc/puma.rb",
        ),
        "workhorse-internal": base
        + workhorse
        + (
            "-listenNetwork",
            "unix",
            "-listenAddr",
            "/var/opt/gitlab/gitlab-workhorse/sockets/socket",
        )
        + backend,
        "workhorse": base
        + workhorse
        + (
            "-listenNetwork",
            "tcp",
            "-listenAddr",
            f"127.0.0.1:{spec.ports.web}",
        )
        + backend,
    }
