"""Collect bounded kernel diagnostics without changing original exceptions."""

from dataclasses import dataclass
from pathlib import Path

from lab_generate_skill.ports.lifecycle import OperationControl
from .kernel_files import KernelControl, KernelRead, inspect_control, read_kernel_file


@dataclass(frozen=True)
class KernelPinnedControl:
    phase: str
    directory: KernelControl
    events: KernelControl
    directory_link: str
    events_link: str
    events_errno: int | None


@dataclass(frozen=True)
class KernelCapture:
    reads: tuple[KernelRead, ...]
    controls: tuple[KernelControl, ...]
    failed_control_path: str | None = None
    pinned_controls: tuple[KernelPinnedControl, ...] = ()


class KernelReadings:
    def __init__(self, control: OperationControl) -> None:
        self.control = control
        self.reads: list[KernelRead] = []
        self.controls: list[KernelControl] = []
        self.failed_control_path: str | None = None

    def read(self, path: Path, limit: int) -> bytes:
        try:
            result = read_kernel_file(path, limit, self.control)
        except BaseException as error:
            failed = getattr(error, "kernel_read_capture", None)
            if isinstance(failed, KernelRead):
                self.reads.append(failed)
            raise
        self.reads.append(result)
        return result.content

    def inspect(self, path: Path, *, directory: bool) -> KernelControl:
        try:
            result = inspect_control(path, self.control, directory=directory)
        except BaseException as error:
            self.failed_control_path = str(path)
            failed = getattr(error, "kernel_control_capture", None)
            if isinstance(failed, KernelControl):
                self.controls.append(failed)
            raise
        self.controls.append(result)
        return result

    def capture(self) -> KernelCapture:
        return KernelCapture(
            tuple(self.reads), tuple(self.controls), self.failed_control_path
        )
