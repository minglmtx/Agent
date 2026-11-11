"""Fixed argv; all writable application paths bind to this private instance."""

from .service_contract import ShoppingServiceSpec


def container(
    spec: ShoppingServiceSpec,
    *,
    seeded: bool = True,
    search: bool = False,
    snapshot: bool = False,
) -> tuple[str, ...]:
    spec = ShoppingServiceSpec.model_validate(spec)
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
    for source, target in (
        (spec.files.state_root, "/state"),
        (spec.control_root, "/control"),
        (spec.runtime_root, "/runtime"),
    ):
        args += (
            "--bind",
            source + ":" + target + (":ro" if target == "/control" else ""),
        )
    if seeded:
        for source, target in (
            ("mysql", "/var/lib/mysql"),
            ("etc", "/var/www/magento2/app/etc"),
            ("generated", "/var/www/magento2/generated"),
            ("var", "/var/www/magento2/var"),
            ("search/config", "/usr/share/java/elasticsearch/config"),
            ("search/data", "/usr/share/java/elasticsearch/data"),
            ("search/logs", "/usr/share/java/elasticsearch/logs"),
            ("tmp", "/tmp"),
            ("var-tmp", "/var/tmp"),
            (
                "native-static/Magento_OfflinePayments",
                "/var/www/magento2/pub/static/frontend/Magento/blank/en_US/Magento_OfflinePayments:ro",
            ),
        ):
            args += ("--bind", spec.files.state_root + "/" + source + ":" + target)
    if search:
        args += ("--env", "ES_JAVA_HOME=/usr", "--env", "ES_TMPDIR=/state/search/tmp")
    if snapshot:
        args += ("--bind", spec.snapshot_root + ":/snapshot")
    return args + (spec.files.image_path,)


def service_commands(spec: ShoppingServiceSpec) -> dict[str, tuple[str, ...]]:
    spec = ShoppingServiceSpec.model_validate(spec)
    base = container(spec)
    return {
        "mysql": base
        + (
            "mysqld",
            "--no-defaults",
            "--datadir=/state/mysql",
            "--tmpdir=/state/mysql-tmp",
            "--socket=/runtime/mysql.sock",
            "--pid-file=/runtime/mysql.pid",
            "--bind-address=127.0.0.1",
            f"--port={spec.ports.database}",
            "--innodb-buffer-pool-size=256M",
        ),
        # Persist the original RAM cache/session data on normal TERM so that the
        # stopped-directory snapshot also covers Redis, rather than discarding it.
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
            "900 1",
            "--appendonly",
            "no",
            "--dbfilename",
            "dump.rdb",
        ),
        "search": container(spec, search=True) + ("elasticsearch",),
        "php": base + ("php-fpm", "--nodaemonize", "--fpm-config", "/control/php.conf"),
        "nginx": base
        + (
            "nginx",
            "-e",
            "/runtime/nginx-error.log",
            "-c",
            "/control/nginx.conf",
            "-g",
            "daemon off;",
        ),
    }
