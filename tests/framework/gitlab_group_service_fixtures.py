"""Synthetic services bound to original fixture worker, not real native processes."""

from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from gitlab_native_fixtures import Group


class OriginalFixtureGroup(Group):
    def __init__(self, generation: int, owner: ProcessOwnerGuard | None) -> None:
        super().__init__(generation)
        self.original_owner = owner

    def pin_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceIdentity:
        original = super().pin_namespace(name, control)
        if self.original_owner is None:
            return original
        worker = self.original_owner.worker
        offset = 10000 + self.generation * 100 + self.names.index(name) * 10
        pinned = original.model_copy(
            update={
                "launcher": worker.model_copy(
                    update={
                        "process_id": worker.process_id + offset,
                        "start_ticks": worker.start_ticks + offset,
                    }
                ),
                "init": worker.model_copy(
                    update={
                        "process_id": worker.process_id + offset + 1,
                        "start_ticks": worker.start_ticks + offset + 1,
                    }
                ),
            }
        )
        self.pins[-1] = pinned
        return pinned
