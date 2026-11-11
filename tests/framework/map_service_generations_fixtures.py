"""Per-service synthetic groups behind real owned Map generation composition."""

from pathlib import Path
from typing import Any
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.domain.native_namespace import NativeNamespaceStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from lab_generate_skill.adapters.map_runtime.services import OwnedMapServices
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from map_services_fixtures import Group
from map_instance_fixtures import InstanceCase


class OneGroup(Group):
    def __init__(self, case: InstanceCase, number: int) -> None:
        super().__init__(case.spec)
        self.generation = number
        self.retire_error: BaseException | None = None
        self.force_error: BaseException | None = None
        self.close_error: BaseException | None = None
        self.close_calls = 0
        self.force_calls = 0
        self.quiet_calls = 0
        self.quiet_result: NativeServiceQuiescence | None = None
        self.force_result: NativeNamespaceStopped | None = None

    def start(
        self, name: str, argv: tuple[str, ...], control: OperationControl
    ) -> None:
        super().start(name, argv, control)
        self.masters[name] = 1000 + self.names.index(name) * 10 + self.generation * 100

    def quiesce(self, control: OperationControl) -> NativeServiceQuiescence:
        self.quiet_calls += 1
        control.checkpoint()
        if self.retire_error is not None:
            raise self.retire_error
        result = self.quiet_result or super().quiesce(control)
        return result

    def stop_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceStopped:
        self.force_calls += 1
        control.checkpoint()
        if self.force_error is not None:
            raise self.force_error
        return self.force_result or NativeNamespaceStopped(
            original=self.pins[0], init_exit_observed=True, launcher_returncode=0
        )

    def stop(self, control: OperationControl) -> Any:
        self.close_calls += 1
        result = super().stop(control)
        if self.close_error is not None:
            raise self.close_error
        return result


class GenerationCase:
    def __init__(self, case: InstanceCase) -> None:
        self.case = case
        self.groups: list[OneGroup] = []
        self.owned: OwnedMapServices | None = None
        self.instance = case.build(services=self.services)

    def factory(self, path: Path) -> QuiescentNativeServices:
        assert path.is_dir() and not list(path.iterdir())
        group = OneGroup(self.case, len(self.groups))
        self.groups.append(group)
        return group

    def services(self, root: str, control: OperationControl) -> OwnedMapServices:
        control.checkpoint()
        self.owned = OwnedMapServices(
            Path(root), BoundedMapStartupControls(), factory=self.factory
        )
        return self.owned

    def close_sockets(self) -> None:
        for group in self.groups:
            for handle in group.sockets:
                handle.close()

    def rails(self) -> OneGroup:
        return next(g for g in reversed(self.groups) if g.names == ["rails_server"])

    def force(self) -> None:
        self.rails().retire_error = OperationStopped(
            "DEADLINE_EXCEEDED", "map-frontend_grace"
        )
