"""Fake original effects plus exact retained native logs, never live authority."""

from pathlib import Path
import json
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.ports.lifecycle import OperationControl
from gitlab_native_fixtures import Group

FIXTURES = Path(__file__).parent / "fixtures"


class ShutdownGroup(Group):
    def __init__(self, generation: int, root: Path) -> None:
        super().__init__(generation)
        (root / "gitaly.log").write_bytes(
            (FIXTURES / "gitlab-4790081-gitaly-stop.log").read_bytes()
        )
        for name in ("workhorse", "workhorse-internal"):
            (root / (name + ".log")).write_bytes(
                (FIXTURES / "gitlab-4790431-workhorse-10s.log").read_bytes()
            )

    def quiesce(self, control: OperationControl) -> NativeServiceQuiescence:
        value = super().quiesce(control).model_dump(mode="json")
        for row in value["masters"]:
            if row["service"] in ("workhorse", "workhorse-internal"):
                row["returncode"] = 1
        for row in value["namespaces"]:
            if row["original"]["service"] in ("workhorse", "workhorse-internal"):
                row["launcher_returncode"] = 1
        return NativeServiceQuiescence.model_validate_json(json.dumps(value))
