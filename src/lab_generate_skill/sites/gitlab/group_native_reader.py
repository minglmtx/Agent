"""Read selected native group facts through the existing supervised command port."""

from collections.abc import Callable
import json
import re
from lab_generate_skill.domain.evidence_io import MAX_OBJECT_BYTES
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_input_commands import NativeInputCommands
from .service_contract import GitlabServiceSpec
from .service_commands import container, RUBY
from .group_sql_capture import GROUP_CAPTURE
from .tasks.group_spec import GroupSpec
from .tasks.group_state import GroupNativeState


class GitlabGroupNativeReader:
    def __init__(
        self,
        services: GitlabServiceSpec,
        commands: NativeInputCommands,
        decode: Callable[[bytes, GroupSpec], GroupNativeState],
    ) -> None:
        self.services = GitlabServiceSpec.model_validate(services)
        self.commands, self.decode = commands, decode
        self.captured_raw: bytes | None = None

    def capture(
        self, spec: GroupSpec, username: str, control: OperationControl
    ) -> GroupNativeState:
        self.captured_raw = None
        spec = GroupSpec.model_validate(spec)
        if (
            type(username) is not str
            or not 0 < len(username) <= 255
            or re.fullmatch(r"[A-Za-z0-9_.-]+", username) is None
        ):
            raise ValueError("Original ordinary native group username required")
        data = json.dumps(
            {
                "task": spec.task.model_dump(mode="json"),
                "username": username,
                "with_settings": spec.requirements.settings is not None,
            },
            separators=(",", ":"),
        ).encode()
        control.checkpoint()
        raw = self.commands.run_input(
            container(self.services) + (RUBY, "-e", GROUP_CAPTURE), data, control
        )
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_OBJECT_BYTES:
            raise ValueError(
                "Complete native group capture outside private CAS boundary"
            )
        self.captured_raw = raw
        state = self.decode(raw, spec)
        if state.task != spec.task or state.user.username != username:
            raise ValueError("Native group capture changed original task/account")
        control.checkpoint()
        return state
