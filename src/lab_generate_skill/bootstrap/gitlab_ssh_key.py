"""Read bounded native GitLab bytes and bind explicit approved public inputs."""

from lab_generate_skill.adapters.plans.native_input import decode_native_object
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.gitlab.tasks.ssh_key_input import bind_ssh_key_inputs
from lab_generate_skill.sites.gitlab.tasks.ssh_key_spec import SshKeyInputs


def load_ssh_key_inputs(
    raw: bytes, reference: EvidenceRef, public_task: PublicTask
) -> SshKeyInputs:
    try:
        native = decode_native_object(
            raw, reference, content_schema="gitlab-native-contract/1"
        )
        return bind_ssh_key_inputs(native, reference, public_task)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise EvidenceIntegrityError("Invalid original GitLab SSH-key input") from error
