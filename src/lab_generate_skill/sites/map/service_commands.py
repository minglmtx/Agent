"""Fixed original Map native commands, exclusively bound to this node clone."""

from typing import Literal
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.map_runtime_inputs import MapImageRole

SERVICE_NAMES = (
    "search_postgres",
    "search_http",
    "route_car",
    "route_bike",
    "route_foot",
    "tile_postgres",
    "renderd",
    "tile_http",
    "app_postgres",
    "rails_server",
)


def container(
    spec: MapServiceSpec, role: MapImageRole, *, app: bool = False, apache: bool = False
) -> tuple[str, ...]:
    spec = MapServiceSpec.model_validate(spec)
    if (
        role not in ("db", "web", "nominatim", "osrm", "tiles")
        or type(app) is not bool
        or type(apache) is not bool
    ):
        raise ValueError("Explicit native Map image/mount phase required")
    if app and role != "web" or apache and role != "tiles":
        raise ValueError("Map image does not implement the requested mount phase")
    service: Literal["frontend", "search", "tiles"] = (
        "frontend"
        if role in ("db", "web")
        else "tiles" if role == "tiles" else "search"
    )
    state = spec.state_root(service)
    args: tuple[str, ...] = (
        spec.apptainer,
        "exec",
        "--cleanenv",
        "--containall",
        "--no-home",
        "--no-mount",
        "bind-paths,hostfs,cwd",
        "--bind",
        state + ":/state",
        "--bind",
        state + "/tmp:/tmp",
        "--bind",
        state + "/hosts:/etc/hosts:ro",
        "--pwd",
        "/state",
    )
    if role == "db":
        args += ("--bind", spec.inputs.node_tree("app") + "/postgres:/state/pg")
    elif role == "nominatim":
        args += (
            "--bind",
            spec.inputs.node_tree("search") + "/postgres:/state/postgres",
        )
    elif role == "tiles":
        args += ("--bind", spec.inputs.node_tree("tiles") + "/postgres:/state/postgres")
    elif role == "osrm":
        args += ("--bind", spec.inputs.node_tree("routing") + ":/data:ro")
    if role == "web":
        args += ("--bind", spec.inputs.node_tree("frontend") + ":/state/app")
        if app:
            args += (
                "--bind",
                spec.inputs.node_tree("frontend") + ":/app",
                "--pwd",
                "/app",
                "--bind",
                state + "/database.yml:/app/config/database.yml:ro",
                "--bind",
                state + "/settings.local.yml:/app/config/settings.local.yml:ro",
                "--env",
                "RAILS_ENV=development",
                "--env",
                "DISABLE_SPRING=1",
                "--env",
                "WEB_CONCURRENCY=0",
            )
    if apache:
        args += (
            "--env",
            "APACHE_RUN_DIR=/state/run",
            "--env",
            "APACHE_LOCK_DIR=/state/run",
            "--env",
            "APACHE_LOG_DIR=/state/log",
        )
    return args + (spec.inputs.node_image(role),)


def service_commands(spec: MapServiceSpec) -> dict[str, tuple[str, ...]]:
    spec = MapServiceSpec.model_validate(spec)
    search, tiles = container(spec, "nominatim"), container(spec, "tiles")
    commands = {
        "search_postgres": search
        + (
            "/usr/lib/postgresql/14/bin/postgres",
            "-D",
            "/state/postgres",
            "-c",
            "config_file=/state/postgresql.conf",
        ),
        "search_http": search
        + (
            "php",
            "-S",
            f"127.0.0.1:{spec.ports.search}",
            "-t",
            "/state/project/website",
            "/state/project/router.php",
        ),
        **{
            f"route_{profile}": container(spec, "osrm")
            + (
                "osrm-routed",
                "--algorithm",
                "mld",
                "--mmap",
                "--threads",
                "1",
                "--ip",
                "127.0.0.1",
                "--port",
                str(getattr(spec.ports, profile)),
                f"/data/{profile}/us-northeast-latest.osrm",
            )
            for profile in ("car", "bike", "foot")
        },
        "tile_postgres": tiles
        + (
            "/usr/lib/postgresql/15/bin/postgres",
            "-D",
            "/state/postgres",
            "-c",
            "config_file=/state/postgresql.conf",
        ),
        "renderd": tiles + ("renderd", "-f", "-c", "/state/renderd.conf"),
        "tile_http": container(spec, "tiles", apache=True)
        + ("apache2", "-DFOREGROUND", "-f", "/state/apache.conf"),
        "app_postgres": container(spec, "db")
        + (
            "postgres",
            "-D",
            "/state/pg",
            "-c",
            "listen_addresses=",
            "-c",
            "unix_socket_directories=/state/run",
            "-c",
            "shared_buffers=128MB",
        ),
        "rails_server": container(spec, "web", app=True)
        + (
            "bundle",
            "exec",
            "rails",
            "server",
            "-b",
            "127.0.0.1",
            "-p",
            str(spec.ports.web),
        ),
    }
    return commands


def setup_commands(spec: MapServiceSpec) -> dict[str, tuple[str, ...]]:
    return {
        "search_refresh": container(spec, "nominatim")
        + ("nominatim", "refresh", "--project-dir", "/state/project", "--website"),
        "copy_style": container(spec, "tiles")
        + ("cp", "-a", "/home/renderer/src/openstreetmap-carto-backup", "/state/style"),
        "compile_style": container(spec, "tiles")
        + ("sh", "-ec", "cd /state/style; carto project.mml > mapnik.xml"),
        "apache_check": container(spec, "tiles", apache=True)
        + ("apache2", "-t", "-f", "/state/apache.conf"),
        "copy_modules": container(spec, "web")
        + (
            "sh",
            "-ec",
            "test ! -e /state/app/node_modules; cp -a /app/node_modules /state/app/node_modules",
        ),
        "bundle_check": container(spec, "web", app=True) + ("bundle", "check"),
    }
