"""Synthetic Shopping native ports; no real database, service or authority."""

from pathlib import Path
import json
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.domain.native_namespace import (
    NativeNamespaceIdentity,
    NativeNamespaceStopped,
)
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.service_contract import (
    ShoppingPorts,
    ShoppingServiceSpec,
)
from lab_generate_skill.sites.shopping.service_programs import SEED, CONFIGURE, HEALTH
from lab_generate_skill.sites.shopping.snapshot_program import INVENTORY
from lab_generate_skill.sites.shopping.snapshot import ShoppingInventory
from lab_generate_skill.sites.shopping.static_program import NATIVE_STATIC


def plan(root: Path) -> SiteFilesPlan:
    return SiteFilesPlan(
        instance_id="shopping-unit",
        workspace_root="/workspace",
        source_path="/workspace/shopping.sif",
        node_root=str(root),
        image=ReleaseFile(
            path="shopping.sif", size_bytes=1, sha256="a" * 64, executable=False
        ),
    )


def spec(root: Path) -> ShoppingServiceSpec:
    return ShoppingServiceSpec(
        files=plan(root),
        ports=ShoppingPorts(
            web=12001, database=12002, redis=12003, search=12004, transport=12005
        ),
    )


class Commands:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[tuple[str, ...]] = []
        self.error: str | None = None
        self.health = b"ready"
        self.inventory = ShoppingInventory(
            sha256="b" * 64, files=1, directories=1, bytes=1
        )
        self.scans: list[ShoppingInventory] = []

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        self.calls.append(argv)
        if self.error is not None and self.error in argv:
            raise OSError("injected native command failure")
        if SEED in argv and "-ec" in argv:
            config = self.root / "state/search/config"
            config.mkdir(parents=True)
            (config / "elasticsearch.yml").write_text(
                "cluster.name: native\nhttp.port: 9200\n"
            )
            (self.root / "state/fastcgi_params").write_bytes(
                b"# original native FastCGI params\n"
            )
        if CONFIGURE in argv:
            return b"configured"
        if HEALTH in argv:
            return self.health
        if NATIVE_STATIC in argv:
            return json.dumps(
                {
                    "Magento_OfflinePayments": {
                        "installed_source": "/var/www/magento2/vendor/magento/module-offline-payments/view/frontend/web",
                        "original_published_namespace": "/var/www/magento2/pub/static/frontend/Magento/blank/en_US/Magento_OfflinePayments",
                        "original_published_sha256": {"old.js": "a" * 64},
                        "added_installed_sha256": {"new.js": "b" * 64},
                        "native_bytes_only": True,
                        "original_published_bytes_unchanged": True,
                        "external_source_used": False,
                    }
                }
            ).encode()
        if INVENTORY in argv:
            value = self.scans.pop(0) if self.scans else self.inventory
            return value.model_dump_json().encode()
        return b""


class Group:
    def __init__(self, generation: int = 0) -> None:
        self.generation = generation
        self.names: list[str] = []
        self.pins: list[NativeNamespaceIdentity] = []
        self.fail: str | None = None
        self.quiesced = False
        self.stopped = False
        self.exitcode = 0

    def start(
        self, name: str, argv: tuple[str, ...], control: OperationControl
    ) -> None:
        control.checkpoint()
        self.names.append(name)
        if self.fail == name:
            raise OSError("injected native start failure")

    def require_running(self) -> None:
        assert not self.quiesced and not self.stopped

    def pin_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceIdentity:
        control.checkpoint()
        i = self.names.index(name) * 10 + self.generation * 100
        result = NativeNamespaceIdentity(
            service=name,
            launcher=ProcessIdentity(
                node_id="node", boot_id="boot", process_id=1000 + i, start_ticks=100
            ),
            init=ProcessIdentity(
                node_id="node", boot_id="boot", process_id=1001 + i, start_ticks=101
            ),
            namespace_device=4,
            namespace_inode=500 + i,
        )
        self.pins.append(result)
        if self.fail == "pin-" + name:
            raise OSError("injected namespace pin failure")
        return result

    def stop_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceStopped:
        raise AssertionError("Synthetic graceful protocol cannot force stop namespaces")

    def quiesce(self, control: OperationControl) -> NativeServiceQuiescence:
        control.checkpoint()
        self.quiesced = True
        if self.fail == "quiesce":
            raise TimeoutError("original native stop unknown")
        return NativeServiceQuiescence(
            masters=tuple(
                NativeServiceExit(
                    service=x.service,
                    process_id=x.launcher.process_id,
                    returncode=self.exitcode,
                    state="reaped",
                    kill_requested=False,
                )
                for x in self.pins
            ),
            namespaces=tuple(
                NativeNamespaceStopped(
                    original=x,
                    init_exit_observed=True,
                    launcher_returncode=self.exitcode,
                )
                for x in self.pins
            ),
        )

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        control.checkpoint()
        self.stopped = True
        return ()
