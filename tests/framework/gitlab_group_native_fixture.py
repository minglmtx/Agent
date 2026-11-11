"""Tiny real PG; only mount prefix adapts, production Group/CSV commands unchanged.

No benchmark database, original source execution, full site or Actor. The
workspace SIF is consumed directly as in the accepted SSH tiny fixture.
"""

from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.bootstrap.gitlab_group_state import load_group_state
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.service_contract import GitlabServiceSpec
from lab_generate_skill.sites.gitlab.service_commands import container
from lab_generate_skill.sites.gitlab.group_capture_reader import GroupCaptureReader
from lab_generate_skill.sites.gitlab.group_native_reader import GitlabGroupNativeReader
from lab_generate_skill.sites.gitlab.project_copy import GitlabProjectCopyReader
from gitlab_ssh_native_fixture import TinyNative, literal
from gitlab_native_fixtures import spec


def schema_sql() -> bytes:
    return b"""CREATE TABLE users (id integer PRIMARY KEY,username text UNIQUE NOT NULL);
CREATE TABLE namespaces (id integer PRIMARY KEY,name text,path text,type text,visibility_level integer,parent_id integer);
CREATE TABLE members (id integer PRIMARY KEY,source_id integer,user_id integer,access_level integer,type text);
CREATE TABLE namespace_settings (namespace_id integer PRIMARY KEY,setup_for_company boolean,jobs_to_be_done integer);
CREATE TABLE projects (id integer PRIMARY KEY,namespace_id integer,name text,path text);
INSERT INTO users VALUES (1,'native-user'),(2,'other-user');
INSERT INTO namespaces VALUES (10,'Existing','existing','Group',20,NULL),(11,'Personal','personal','User',0,NULL);
INSERT INTO members VALUES (10,10,2,50,'GroupMember'),(11,11,1,40,'ProjectMember');
INSERT INTO namespace_settings VALUES (10,false,NULL),(11,false,2);
INSERT INTO projects VALUES (1,10,'Original, project','original'),(2,11,E'Line\\nbreak','second');
"""


class GroupNativeInputs:
    def __init__(self, native: TinyNative, services: GitlabServiceSpec) -> None:
        self.native, self.expected = native, container(services)
        self.calls: list[tuple[tuple[str, ...], bytes]] = []

    def run_input(
        self, argv: tuple[str, ...], data: bytes, control: OperationControl
    ) -> bytes:
        assert argv[: len(self.expected)] == self.expected
        self.calls.append((argv, data))
        return self.native.inputs.run_input(
            self.native.prefix + argv[len(self.expected) :], data, control
        )


class TinyGroup:
    def __init__(self, root: Path) -> None:
        self.native = TinyNative(root)
        self.services = spec(root / "declared-component")
        self.inputs = GroupNativeInputs(self.native, self.services)
        self.reader = GroupCaptureReader(
            GitlabGroupNativeReader(self.services, self.inputs, load_group_state),
            GitlabProjectCopyReader(self.services, self.inputs, SystemClock()),
            load_group_capture,
        )

    def initialize(self, control: OperationControl) -> None:
        self.native.initialize_database(control)
        self.native.sql(schema_sql(), control)

    def add_selected_group(self, control: OperationControl) -> None:
        self.native.sql(
            b"INSERT INTO namespaces VALUES (20,'Development Team','development-team','Group',0,NULL);\nINSERT INTO members VALUES (20,20,1,50,'GroupMember');\nINSERT INTO namespace_settings VALUES (20,true,3);\n",
            control,
        )
