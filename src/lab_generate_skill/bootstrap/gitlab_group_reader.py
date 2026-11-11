"""Fixed Group readers/decoders/time bounds, assembled before task dispatch."""

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.ports.native_input_commands import NativeInputCommands
from lab_generate_skill.sites.gitlab.service_contract import GitlabServiceSpec
from lab_generate_skill.sites.gitlab.group_native_reader import GitlabGroupNativeReader
from lab_generate_skill.sites.gitlab.project_copy import GitlabProjectCopyReader
from lab_generate_skill.sites.gitlab.group_capture_reader import GroupCaptureReader
from .gitlab_group_state import load_group_state
from .gitlab_group_capture import load_group_capture


def build_group_reader(
    services: GitlabServiceSpec, commands: NativeInputCommands
) -> GroupCaptureReader:
    return GroupCaptureReader(
        GitlabGroupNativeReader(services, commands, load_group_state),
        GitlabProjectCopyReader(services, commands, SystemClock()),
        load_group_capture,
    )
