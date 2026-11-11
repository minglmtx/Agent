"""Private original lineage and already-public parameters; unadmitted only."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract, NonEmptyText
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from .ssh_key_parameters import SshKeyParameters, render_public_goal

OUTPUT_REQUIREMENTS = (
    "Finish with send_msg_to_user after checking whether the supplied SSH key was saved.",
)


class SshKeySpec(Contract):
    schema_version: Literal["gitlab-profile-ssh-key/1"] = "gitlab-profile-ssh-key/1"
    task: TaskIdentity
    native_contract_ref: EvidenceRef
    legacy_runtime_task_id: NonEmptyText
    native_goal: NonEmptyText
    parameters: SshKeyParameters
    admission: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def selected_family(self) -> Self:
        if (
            self.task.site,
            self.task.family,
            self.task.contract_version,
            self.task.split,
        ) != ("gitlab", "profile_ssh_key", 1, "train"):
            raise ValueError("Expected selected derived train GitLab SSH-key family")
        if (
            self.native_contract_ref.visibility,
            self.native_contract_ref.content_schema,
            self.native_contract_ref.media_type,
        ) != ("private", "gitlab-native-contract/1", "application/json"):
            raise ValueError("Original GitLab contract must remain private JSON")
        if (
            self.legacy_runtime_task_id
            != self.task.source_task_id + "--public-cpu-candidate-v1"
        ):
            raise ValueError(
                "Historical GitLab derivative has different source lineage"
            )
        return self


class SshKeyInputs(Contract):
    schema_version: Literal["gitlab-profile-ssh-key-inputs/1"] = (
        "gitlab-profile-ssh-key-inputs/1"
    )
    public_task: PublicTask
    private_spec: SshKeySpec

    @model_validator(mode="after")
    def same_task(self) -> Self:
        if self.public_task.identity != self.private_spec.task:
            raise ValueError(
                "Public and private GitLab inputs identify different tasks"
            )
        if self.public_task.goal != render_public_goal(
            self.private_spec.native_goal, self.private_spec.parameters
        ):
            raise ValueError("Public task omitted or changed supplied key/title")
        return self
