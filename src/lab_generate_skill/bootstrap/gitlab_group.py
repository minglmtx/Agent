"""Bind exact original group bytes without granting historical admission."""

from lab_generate_skill.adapters.plans.native_input import decode_native_object
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.gitlab.tasks.group_input import bind_group_inputs
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec


def load_group_inputs(
    raw: bytes, reference: EvidenceRef, public_task: PublicTask
) -> GroupSpec:
    try:
        native = decode_native_object(
            raw, reference, content_schema="gitlab-native-contract/1"
        )
        return bind_group_inputs(native, reference, public_task)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise EvidenceIntegrityError("Invalid original GitLab group input") from error
