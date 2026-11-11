"""Only original native3 argv and exact private writable mounts."""

from typing import Literal
from .service_contract import RedditServiceSpec

SERVICE_NAMES = ("postgres", "php", "nginx")


def container(
    spec: RedditServiceSpec,
    *,
    seeded: bool = True,
    snapshot: Literal["none", "save", "read"] = "none",
    native_input: bool = False,
) -> tuple[str, ...]:
    spec = RedditServiceSpec.model_validate_json(spec.model_dump_json())
    if (
        type(seeded) is not bool
        or type(native_input) is not bool
        or snapshot not in ("none", "save", "read")
    ):
        raise ValueError("Explicit native Reddit mount phase required")
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
    )
    for source, target, mode in [
        (spec.files.state_root, "/state", ""),
        (spec.control_root, "/control", ":ro"),
        (spec.runtime_root, "/runtime", ""),
    ]:
        args += ("--bind", source + ":" + target + mode)
    if seeded:
        for source, target in [
            ("postgres", "/usr/local/pgsql/data"),
            ("app.env", "/var/www/html/.env"),
            ("var", "/var/www/html/var"),
            ("tmp", "/tmp"),
            ("var-tmp", "/var/tmp"),
        ]:
            args += ("--bind", spec.files.state_root + "/" + source + ":" + target)
    if snapshot != "none":
        args += (
            "--bind",
            spec.snapshot_root + ":/snapshot" + (":ro" if snapshot == "read" else ""),
        )
    if native_input:
        args += ("--bind", spec.native_input_root + ":/native-input:ro")
    return args + (spec.files.image_path,)


def service_commands(spec: RedditServiceSpec) -> dict[str, tuple[str, ...]]:
    base = container(spec)
    return {
        "postgres": base
        + (
            "/usr/bin/postgres",
            "-D",
            "/state/postgres",
            "-p",
            str(spec.ports.database),
            "-c",
            "listen_addresses=",
            "-c",
            "unix_socket_directories=/runtime",
            "-c",
            "hba_file=/control/pg_hba.conf",
        ),
        "php": base
        + (
            "/usr/local/sbin/php-fpm",
            "--nodaemonize",
            "--fpm-config",
            "/control/php.conf",
        ),
        "nginx": base
        + (
            "/usr/sbin/nginx",
            "-e",
            "/runtime/nginx-error.log",
            "-c",
            "/control/nginx.conf",
            "-g",
            "daemon off;",
        ),
    }
