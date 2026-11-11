"""Small real PostgreSQL/repository fixture; never a benchmark site or Actor.

The fixed workspace SIF is read directly for this tiny component fixture. This
does not validate production image staging or the registered site resource.
"""

import json
from pathlib import Path
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.native_input_commands import (
    CheckedNativeInputCommands,
)
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.tasks.ssh_key_state import (
    PROTECTED_TABLES,
    AUTH_COLUMNS,
)
from lab_generate_skill.sites.gitlab.ssh_native_reader import CAPTURE
from lab_generate_skill.sites.gitlab.service_commands import RUBY
from gitlab_programs_live import IMAGE
from gitlab_ssh_state_fixtures import native_state, selected_spec

PG = "/opt/gitlab/embedded/bin/"


def literal(value: object) -> str:
    if value is None:
        return "NULL"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if type(value) is str and "\0" not in value:
        return "'" + value.replace("'", "''") + "'"
    raise ValueError("Unsupported tiny native fixture scalar")


def schema_sql() -> bytes:
    state = native_state()
    users_types = {
        "id": "integer PRIMARY KEY",
        "username": "text UNIQUE NOT NULL",
        "admin": "boolean NOT NULL",
        "external": "boolean NOT NULL",
        "state": "text NOT NULL",
        "name": "text",
        **{field: "text" for field in AUTH_COLUMNS},
        "sign_in_count": "integer",
    }
    keys_types = {
        name: (
            "integer PRIMARY KEY"
            if name == "id"
            else "integer" if name == "user_id" else "text"
        )
        for name in state.keys.columns
    }
    sql = []
    for table in PROTECTED_TABLES:
        columns = (
            users_types
            if table == "users"
            else {"id": "integer PRIMARY KEY", "value": "text"}
        )
        sql.append(
            'CREATE TABLE "'
            + table
            + '" ('
            + ",".join('"' + name + '" ' + kind for name, kind in columns.items())
            + ");"
        )
    sql.append(
        "CREATE TABLE keys ("
        + ",".join('"' + name + '" ' + kind for name, kind in keys_types.items())
        + ");"
    )
    for native_table in (state.users, state.keys):
        for row in native_table.rows:
            sql.append(
                'INSERT INTO "'
                + native_table.table
                + '" ('
                + ",".join('"' + name + '"' for name in native_table.columns)
                + ") VALUES ("
                + ",".join(literal(row[name]) for name in native_table.columns)
                + ");"
            )
    for table in PROTECTED_TABLES:
        if table != "users":
            sql.append('INSERT INTO "' + table + "\" VALUES (1,'original');")
    return ("\n".join(sql) + "\n").encode()


class TinyNative:
    def __init__(self, root: Path) -> None:
        self.root = root
        for name in (
            "data/postgresql",
            "data/git-data/repositories",
            "control",
            "logs",
        ):
            (root / name).mkdir(parents=True, mode=0o700)
        self.prefix = (
            "/usr/bin/apptainer",
            "exec",
            "--cleanenv",
            "--containall",
            "--no-home",
            "--no-mount",
            "bind-paths,hostfs,cwd",
            "--pwd",
            "/",
            "--bind",
            str(root / "data") + ":/var/opt/gitlab",
            "--bind",
            str(root / "control") + ":/control:ro",
            str(IMAGE),
        )
        self.runner = ProcessRunner(max_output_bytes=64 * 1024 * 1024, reap_timeout=2)
        self.commands = CheckedNativeCommands(self.runner)
        self.inputs = CheckedNativeInputCommands(self.runner)
        self.services = LocalNativeServices(root / "logs")

    def command(self, arguments: tuple[str, ...], control: OperationControl) -> bytes:
        return self.commands.run(self.prefix + arguments, control)

    def sql(self, value: bytes, control: OperationControl) -> bytes:
        return self.inputs.run_input(
            self.prefix
            + (
                PG + "psql",
                "-h",
                "/var/opt/gitlab/postgresql",
                "-U",
                "gitlab",
                "-d",
                "gitlabhq_production",
                "-X",
                "-q",
                "-A",
                "-t",
                "-w",
                "-v",
                "ON_ERROR_STOP=1",
            ),
            value,
            control,
        )

    def initialize(self, control: OperationControl) -> None:
        self.initialize_database(control)
        self.sql(schema_sql(), control)
        self.initialize_repositories(control)

    def initialize_database(self, control: OperationControl) -> None:
        self.command(
            (
                PG + "initdb",
                "-D",
                "/var/opt/gitlab/postgresql/data",
                "-U",
                "gitlab",
                "-A",
                "trust",
                "--no-locale",
                "--encoding=UTF8",
            ),
            control,
        )
        self.services.start(
            "postgres",
            self.prefix
            + (
                PG + "postgres",
                "-D",
                "/var/opt/gitlab/postgresql/data",
                "-c",
                "listen_addresses=",
                "-c",
                "unix_socket_directories=/var/opt/gitlab/postgresql",
            ),
            control,
        )
        # Read-only readiness probes; initialization is issued exactly once.
        for _ in range(60):
            self.services.require_running()
            capture = self.runner.run(
                self.prefix
                + (
                    PG + "pg_isready",
                    "-h",
                    "/var/opt/gitlab/postgresql",
                    "-U",
                    "gitlab",
                ),
                control,
            )
            if capture.returncode == 0:
                break
            control.wait(0.1)
        else:
            raise RuntimeError("Tiny native PostgreSQL readiness not reached")
        self.services.pin_namespace("postgres", control)
        self.command(
            (
                PG + "createdb",
                "-h",
                "/var/opt/gitlab/postgresql",
                "-U",
                "gitlab",
                "gitlabhq_production",
            ),
            control,
        )

    def initialize_repositories(self, control: OperationControl) -> None:
        for relative in (
            "@hashed/ab/cd/project.git",
            "@hashed/ab/cd/project.wiki.git",
            "@pools/aa/bb/pool.git",
        ):
            path = "/var/opt/gitlab/git-data/repositories/" + relative
            self.command(
                (PG + "git", "init", "--bare", "--initial-branch=main", path), control
            )
        path = "/var/opt/gitlab/git-data/repositories/@hashed/ab/cd/project.git"
        tree = (
            self.command((PG + "git", "--git-dir=" + path, "mktree"), control)
            .strip()
            .decode()
        )
        commit = (
            self.command(
                (
                    PG + "git",
                    "--git-dir=" + path,
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@localhost",
                    "commit-tree",
                    tree,
                    "-m",
                    "Original",
                ),
                control,
            )
            .strip()
            .decode()
        )
        self.command(
            (PG + "git", "--git-dir=" + path, "update-ref", "refs/heads/main", commit),
            control,
        )
        cache = (
            self.root
            / "data/git-data/repositories/+gitaly/state/@hashed/aa/bb"
            / ("a" * 64 + ".git")
        )
        cache.mkdir(parents=True)

    def capture(self, control: OperationControl) -> bytes:
        return self.inputs.run_input(
            self.prefix + (RUBY, "-e", CAPTURE),
            json.dumps(
                dict(
                    task=selected_spec().task.model_dump(mode="json"),
                    username="native-user",
                )
            ).encode(),
            control,
        )
