"""Explicit native/public source data for the current engineering entry.

This declaration is not source admission, a task dispatch or permission to
re-execute an unknown. Existing bootstrap decoders bind the original bytes.
"""

from dataclasses import dataclass
import hashlib
from urllib.parse import urlsplit
from lab_generate_skill.bootstrap.gitlab_group import load_group_inputs
from lab_generate_skill.bootstrap.gitlab_ssh_key import load_ssh_key_inputs
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.native_private_json import (
    NativePrivateJsonProfile,
    GITLAB_PRIVATE_JSON,
    GITLAB_GROUP_PRIVATE_JSON,
)
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec
from lab_generate_skill.sites.gitlab.tasks.ssh_key_spec import SshKeySpec
from lab_generate_skill.sites.gitlab.tasks.group_policy import group_initial_spec
from lab_generate_skill.sites.gitlab.tasks.ssh_key_policy import ssh_key_initial_spec


def group_task(identity: TaskIdentity) -> bool:
    identity = TaskIdentity.model_validate(identity)
    if (identity.site, identity.contract_version, identity.split) != (
        "gitlab",
        1,
        "train",
    ):
        raise ValueError("Explicit original train GitLab v1 task required")
    if identity.family not in ("profile_ssh_key", "group_creation"):
        raise ValueError("Unsupported explicit GitLab family")
    return identity.family == "group_creation"


def check_gitlab_task(config: SiteWorkerConfiguration, identity: TaskIdentity) -> bool:
    group = group_task(identity)
    profile = GITLAB_GROUP_PRIVATE_JSON if group else GITLAB_PRIVATE_JSON
    if (
        config.site_id != "gitlab"
        or config.private_evidence is None
        or config.private_evidence.profile != profile
    ):
        raise ValueError("Selected GitLab family changed original private profile")
    return group


@dataclass(frozen=True)
class GitlabSourceSelection:
    native: bytes
    public_template: PublicTask

    def __post_init__(self) -> None:
        if not isinstance(self.public_template, PublicTask):
            raise TypeError("Explicit validated GitLab public template required")
        PublicTask.model_validate(self.public_template)
        if type(self.native) is not bytes or not 0 < len(self.native) <= 1024 * 1024:
            raise ValueError("Bounded original GitLab contract bytes required")
        self.load(self.reference(), self.public_template)

    def reference(self) -> EvidenceRef:
        return EvidenceRef(
            uri="engineering:original-gitlab-selection",
            sha256=hashlib.sha256(self.native).hexdigest(),
            size_bytes=len(self.native),
            media_type="application/json",
            content_schema="gitlab-native-contract/1",
            visibility="private",
            producer="original-gitlab-selection",
        )

    @property
    def group(self) -> bool:
        return group_task(self.public_template.identity)

    def load(
        self, reference: EvidenceRef, public: PublicTask
    ) -> GroupSpec | SshKeySpec:
        if public.identity != self.public_template.identity:
            raise ValueError("GitLab source changed original task identity")
        if self.group:
            return load_group_inputs(self.native, reference, public)
        return load_ssh_key_inputs(self.native, reference, public).private_spec

    @property
    def profile(self) -> NativePrivateJsonProfile:
        return GITLAB_GROUP_PRIVATE_JSON if self.group else GITLAB_PRIVATE_JSON

    @property
    def initial_spec(self) -> InitialStateSpec:
        factory = group_initial_spec if self.group else ssh_key_initial_spec
        return factory(self.public_template.identity)

    def check_configuration(self, config: SiteWorkerConfiguration) -> None:
        check_gitlab_task(config, self.public_template.identity)

    def public_at(self, endpoint: str, actions: tuple[str, ...] | None) -> PublicTask:
        if type(endpoint) is not str:
            raise TypeError("Original allocated GitLab endpoint must be text")
        origin = urlsplit(endpoint)
        if (
            origin.scheme != "http"
            or origin.hostname != "127.0.0.1"
            or origin.port is None
            or not 1024 <= origin.port <= 65535
            or endpoint != f"http://127.0.0.1:{origin.port}/"
        ):
            raise ValueError("Original allocated GitLab root endpoint required")
        original = urlsplit(self.public_template.start_url)
        path = original.path.removeprefix("/")
        suffix = path + ("#" + original.fragment if original.fragment else "")
        public = PublicTask.model_validate(
            self.public_template.model_copy(
                update={
                    "start_url": endpoint + (suffix if self.group else ""),
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


def ssh_selection() -> GitlabSourceSelection:
    from test_gitlab_ssh_key_inputs import FIXTURE, public_task

    return GitlabSourceSelection(FIXTURE.read_bytes(), public_task())


def group_selection() -> GitlabSourceSelection:
    from gitlab_group_fixtures import FIXTURE, public_task

    return GitlabSourceSelection(FIXTURE.read_bytes(), public_task())
