"""Trusted browser setup injected into the adapter, never a model-visible view.

The page is confined to browser-worker setup. This capability is not exposed to
application, collectors or roles and must not create another Observation.
"""

from typing import Any, Protocol
from lab_generate_skill.domain.task import PublicTask
from .lifecycle import OperationControl


class BrowserInitializer(Protocol):
    def setup(self, page: Any, task: PublicTask, control: OperationControl) -> None: ...
