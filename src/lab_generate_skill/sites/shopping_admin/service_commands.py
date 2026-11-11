"""Fixed image-backed commands; endpoint/path strings derive from typed spec only."""

from .service_contract import AdminServiceSpec


def container(
    spec: AdminServiceSpec, *, seeded: bool = True, search: bool = False
) -> tuple[str, ...]:
    spec = AdminServiceSpec.model_validate(spec)
    layout = spec.layout
    args: tuple[str, ...] = (
        layout.apptainer,
        "exec",
        "--cleanenv",
        "--containall",
        "--no-home",
        "--no-mount",
        "bind-paths,hostfs,cwd",
        "--pwd",
        "/",
        "--bind",
        layout.state_root + ":/state",
    )
    if seeded:
        for relative, target in (
            ("app", "/var/www/magento2"),
            ("elasticsearch/config", "/usr/share/java/elasticsearch/config"),
            ("elasticsearch/data", "/usr/share/java/elasticsearch/data"),
            ("elasticsearch/logs", "/usr/share/java/elasticsearch/logs"),
        ):
            args += ("--bind", layout.state_root + "/" + relative + ":" + target)
    if search:
        args += (
            "--env",
            "ES_JAVA_HOME=/usr",
            "--env",
            "ES_TMPDIR=/state/elasticsearch/tmp",
        )
    return args + (layout.image_path,)


def service_commands(spec: AdminServiceSpec) -> dict[str, tuple[str, ...]]:
    spec = AdminServiceSpec.model_validate(spec)
    base = container(spec)
    return {
        "mysql": base
        + (
            "mysqld",
            "--no-defaults",
            "--init-file=/state/database-observer-init.sql",
            "--datadir=/state/mysql",
            "--socket=/state/run/mysql.sock",
            "--pid-file=/state/run/mysql.pid",
            "--bind-address=127.0.0.1",
            f"--port={spec.ports.database}",
            "--innodb-buffer-pool-size=512M",
        ),
        "redis": base
        + (
            "redis-server",
            "--bind",
            "127.0.0.1",
            "--port",
            str(spec.ports.redis),
            "--dir",
            "/state/redis",
            "--save",
            "",
            "--appendonly",
            "no",
        ),
        "search": container(spec, search=True) + ("elasticsearch",),
        "php": base
        + ("php-fpm", "--nodaemonize", "--fpm-config", "/state/php-fpm.conf"),
        "nginx": base
        + (
            "nginx",
            "-e",
            "/state/nginx-error.log",
            "-c",
            "/state/nginx.conf",
            "-g",
            "daemon off;",
        ),
    }
