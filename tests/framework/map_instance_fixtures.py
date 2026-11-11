"""Whole small-tree staging/preparation; explicit synthetic images and services."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_runtime.stage import NodeMapInputs
from lab_generate_skill.adapters.map_runtime import stage
from lab_generate_skill.adapters.map_runtime.layout import NativeMapLayout
from lab_generate_skill.adapters.map_runtime.frontend import NativeMapFrontendFiles
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.adapters.sites.files import NodeSiteFiles
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_services import NativeServices
from lab_generate_skill.sites.map.instance import MapInstance
from map_frontend_fixtures import inputs
from map_services_fixtures import Commands, Group


class Lease:
    def __init__(self, ports: tuple[int, ...]) -> None:
        self.ports = ports
        self.releases = 0

    def release(self, control: OperationControl) -> None:
        self.releases += 1
        pytest.fail("Instance must retain lease until enclosing resource closure")


class Ports:
    def __init__(self, lease: Lease) -> None:
        self.lease = lease
        self.calls = 0

    def reserve(self, count: int, control: OperationControl) -> Lease:
        control.checkpoint()
        assert count == 6
        self.calls += 1
        return self.lease


class InstanceCase:
    def __init__(self, root: Path, patch: pytest.MonkeyPatch) -> None:
        self.spec = inputs(root)
        self.loaded: list[ReleaseFile] = []
        self.group = Group(self.spec)
        self.commands = Commands(self.spec)
        self.ports = Ports(Lease(tuple(self.spec.ports.model_dump().values())))
        self.files = NodeMapInputs()
        self.layout = NativeMapLayout()
        self.frontend = NativeMapFrontendFiles()
        self.factories: list[str] = []

        def common(_self: Any, files: SiteFilesPlan, control: OperationControl) -> None:
            control.checkpoint()
            assert files == self.spec.inputs.files
            target = Path(files.node_root)
            target.mkdir(mode=0o700)
            for name in ("image", "state", "logs"):
                (target / name).mkdir(mode=0o700)
            self.loaded.append(files.image)

        def image(
            source: Path, target: Path, pin: ReleaseFile, control: OperationControl
        ) -> None:
            control.checkpoint()
            expected = next(x for x in self.spec.inputs.images if x.file == pin)
            assert str(source / pin.path) == expected.source_path
            assert target == Path(self.spec.inputs.files.node_root) / "image"
            self.loaded.append(pin)

        patch.setattr(NodeSiteFiles, "stage", common)
        patch.setattr(stage, "copy_pinned_file", image)
        self.instance = self.build()

    def services(self, root: str, control: OperationControl) -> NativeServices:
        control.checkpoint()
        self.factories.append(root)
        assert Path(root).is_dir() and not list(Path(root).iterdir())
        return self.group

    def build(self, **changes: Any) -> MapInstance:
        values: dict[str, Any] = dict(
            inputs=self.spec.inputs,
            files=self.files,
            ports=self.ports,
            layout=self.layout,
            frontend_files=self.frontend,
            commands=self.commands,
            services=self.services,
            limits=BoundedMapStartupControls(),
            hostname="fixture-node",
            host_cpus=128,
        )
        values.update(changes)
        return MapInstance(**values)

    def close_sockets(self) -> None:
        for handle in self.group.sockets:
            handle.close()
