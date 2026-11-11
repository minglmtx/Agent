"""Trusted Group task assembly; cleanup only retains failed-read diagnostics."""

from collections.abc import Callable
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_input_commands import NativeInputCommands
from lab_generate_skill.ports.site_evidence import SitePrivateArtifacts
from lab_generate_skill.sites.gitlab.instance import GitlabInstance
from lab_generate_skill.sites.gitlab.tasks.group_lifecycle import GroupLifecycle
from .gitlab_group_reader import build_group_reader
from .site_private_artifacts import _IndependentCleanupControls


def build_group_lifecycle(
    instance: GitlabInstance,
    commands: NativeInputCommands,
    username: Callable[[OperationControl], str],
    artifacts: SitePrivateArtifacts,
) -> GroupLifecycle:
    assert instance.spec is not None
    return GroupLifecycle(
        instance,
        build_group_reader(instance.spec, commands),
        username,
        artifacts,
        clock=SystemClock(),
        cleanup_controls=_IndependentCleanupControls(),
    )
