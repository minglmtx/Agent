"""Bind the existing browser command authority to one exact allocation."""

from typing import Literal
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.browser_resources import BrowserResourceAuthority
from lab_generate_skill.ports.lifecycle import OperationControl


class BoundBrowserAuthority:
    def __init__(
        self, spec: BrowserResourceSpec, authority: BrowserResourceAuthority
    ) -> None:
        self.spec, self.authority = spec, authority

    def verify(
        self,
        spec: BrowserSessionSpec,
        phase: Literal["start", "step", "close"],
        action: BrowserAction | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if spec != self.spec.configuration.spec:
            raise OwnershipConflict("Browser command changed frozen resource")
        self.spec.check_operation(
            operation, "cleanup" if phase == "close" else "execute"
        )
        self.authority.verify(spec, phase, action, operation, control)
