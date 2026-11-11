"""Optional graceful-stop capability for a consumer's coherent snapshot gate."""

from typing import Protocol
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from .native_services import NativeServices
from .lifecycle import OperationControl


class QuiescentNativeServices(NativeServices, Protocol):
    def quiesce(self, control: OperationControl) -> NativeServiceQuiescence:
        """One TERM attempt; observe all original pinned namespaces, never KILL.

        A timeout/partial stop must not authorize snapshot or restart. The caller
        retains the original handles for independent cleanup and isolation.
        Application consistency (e.g. MySQL normal exit0) is a separate gate.
        """
        ...
