"""Exact complete Group subgroup source data, without execution permission."""

from dataclasses import dataclass
import hashlib
from urllib.parse import urlsplit
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec
from .gitlab_group import load_group_inputs

GROUP_NATIVE_PINS = {
    "286d4ac488bdcd446ffc": "a81355982fc4c6d2c22c32bd35cf599acd84f3fb822fc364fd23ad73e2e0efc2",
    "b45c2140f3e8557e1708": "b97f06e7d7ae684a789b30c46cbeb1823a4bbe18215e3b5fd0f70020d81c9f1c",
    "e4d658cfba6588f6a386": "acd7e87bdbfbe2d18d093135bcbb1940d7cf259a13d7665511be8bc3437ce750",
    "f205b50137926a04a0e3": "230ae6bba309bac26ac69cc5fe70b56cb6eb512e0b7c809b618df49836792729",
}


@dataclass(frozen=True)
class GroupSourceSelection:
    native: bytes
    public_template: PublicTask

    def __post_init__(self) -> None:
        if type(self.native) is not bytes or not 0 < len(self.native) <= 1024**2:
            raise ValueError("Bounded original Group bytes required")
        if not isinstance(self.public_template, PublicTask):
            raise TypeError("Typed original Group public template required")
        t = self.public_template.identity
        if (
            t.task_id != t.source_task_id
            or GROUP_NATIVE_PINS.get(t.source_task_id)
            != hashlib.sha256(self.native).hexdigest()
        ):
            raise ValueError("Exact selected original Group subgroup/native required")
        self.load(self.reference(), self.public_template)

    def reference(self) -> EvidenceRef:
        return EvidenceRef(
            uri="engineering:original-group-source-selection",
            sha256=hashlib.sha256(self.native).hexdigest(),
            size_bytes=len(self.native),
            media_type="application/json",
            content_schema="gitlab-native-contract/1",
            visibility="private",
            producer="original-group-source-selection",
        )

    def load(self, reference: EvidenceRef, public: PublicTask) -> GroupSpec:
        if public.identity != self.public_template.identity:
            raise ValueError("Group source changed original task identity")
        return load_group_inputs(self.native, reference, public)

    def public_at(self, endpoint: str, actions: tuple[str, ...] | None) -> PublicTask:
        if type(endpoint) is not str:
            raise TypeError("Actual allocated Group origin must be text")
        origin = urlsplit(endpoint)
        if (
            origin.scheme != "http"
            or origin.hostname != "127.0.0.1"
            or origin.port is None
            or not 1024 <= origin.port <= 65535
            or endpoint != f"http://127.0.0.1:{origin.port}/"
        ):
            raise ValueError("Canonical allocated private Group origin required")
        original = urlsplit(self.public_template.start_url)
        path = original.path.removeprefix("/") + (
            "#" + original.fragment if original.fragment else ""
        )
        public = PublicTask.model_validate(
            self.public_template.model_copy(
                update={
                    "start_url": endpoint + path,
                    "allowed_actions": (
                        self.public_template.allowed_actions
                        if actions is None
                        else actions
                    ),
                }
            )
        )
        self.load(self.reference(), public)
        return public
