"""Assembly order, partial acquisition ownership and service/port separation."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from site_instance_fixtures import node_path
from lab_generate_skill.adapters.sites.files import NodeSiteFiles
from lab_generate_skill.bootstrap.admin_instance import build_admin_instance
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.instance import AdminInstance
from lab_generate_skill.sites.shopping_admin.instance_contract import AdminInstancePlan
from lab_generate_skill.sites.shopping_admin.service_programs import SEED
from lab_generate_skill.sites.shopping_admin.initial_search import (
    INITIAL_SEARCH_HOLD_PHP,
)
from test_site_files import plan, Stop
from test_admin_services import Commands as ServiceCommands, Services
from test_slurm_commands import guard


class Lease:
    ports = (12001, 12002, 12003, 12004, 12005)
    released = False

    def release(self, control: OperationControl) -> None:
        control.checkpoint()
        self.released = True


class Ports:
    def __init__(self, events: list[str], failure: str | None) -> None:
        self.events, self.failure = events, failure
        self.lease = Lease()

    def reserve(self, count: int, control: OperationControl) -> Lease:
        control.checkpoint()
        self.events.append("ports")
        assert count == 5
        if self.failure == "ports":
            raise OSError("ports failure")
        return self.lease


class Files:
    def __init__(self, events: list[str], failure: str | None) -> None:
        self.events, self.failure = events, failure

    def stage(self, plan: SiteFilesPlan, control: OperationControl) -> None:
        self.events.append("files")
        NodeSiteFiles().stage(plan, control)
        if self.failure == "files":
            raise OSError("files failure")


class Commands(ServiceCommands):
    def __init__(self, root: Path, events: list[str], failure: str | None) -> None:
        super().__init__(root)
        self.events, self.failure = events, failure

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        if "if(false){" + INITIAL_SEARCH_HOLD_PHP + "}" in argv:
            control.checkpoint()
            self.events.append("initial-search-syntax")
            return b""
        if "-n" in argv or any(a.startswith("if(false){") for a in argv):
            control.checkpoint()
            self.events.append("syntax")
            if self.failure == "syntax":
                raise OSError("syntax failure")
            return b""
        if SEED in argv:
            self.events.append("seed")
            assert self.events.count("syntax") == 4
            if self.failure == "seed":
                raise OSError("seed failure")
        return super().run(argv, control)


class Group(Services):
    def __init__(self) -> None:
        super().__init__()
        self.stop_calls = 0
        self.stop_error: BaseException | None = None
        self.unconfirmed = False

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self.stop_calls += 1
        if self.stop_error:
            raise self.stop_error
        control.checkpoint()
        self.stopped = True
        return tuple(
            NativeServiceExit(
                service=name,
                process_id=100 + i,
                returncode=None if self.unconfirmed else 0,
                state="unconfirmed" if self.unconfirmed else "reaped",
                kill_requested=False,
            )
            for i, name in enumerate(self.names)
        )


def instance(
    node_path: Path, failure: str | None = None
) -> tuple[AdminInstance, Ports, Group, list[str]]:
    spec = AdminInstancePlan(files=plan(node_path), apptainer="/usr/bin/apptainer")
    events: list[str] = []
    allocator, group = Ports(events, failure), Group()

    def factory(path: str, control: OperationControl) -> Group:
        control.checkpoint()
        events.append("group")
        assert Path(path).is_dir()
        if failure == "group":
            raise OSError("group failure")
        return group

    site = AdminInstance(
        spec,
        files=Files(events, failure),
        ports=allocator,
        commands=Commands(Path(spec.files.node_root), events, failure),
        services=factory,
    )
    return site, allocator, group, events


def test_prepare_start_stop_same_instance_keeps_ports_and_files(
    node_path: Path,
) -> None:
    site, allocator, group, events = instance(node_path)
    spec = site.prepare(guard())
    assert events[:3] == ["files", "ports", "group"]
    assert events[3:7] == ["syntax"] * 4 and events[7] == "seed"
    assert spec.layout == site.plan.layout and site.spec is spec
    assert site.start(guard()) == spec.admin_url
    assert group.names == ["mysql", "redis", "search", "php", "nginx"]
    assert site.state == "ready"
    facts = site.stop(guard())
    assert site.services is not None and site.services.state == "stopped"
    assert len(facts) == 5 and site.stop(guard()) == facts and group.stop_calls == 1
    assert not allocator.lease.released and Path(site.plan.files.image_path).exists()
    with pytest.raises(RuntimeError):
        site.start(guard())
    with pytest.raises(RuntimeError):
        site.prepare(guard())


@pytest.mark.parametrize("failure", ["files", "ports", "group", "syntax", "seed"])
def test_failed_preparation_retains_partial_owner_and_never_retries(
    node_path: Path, failure: str
) -> None:
    site, allocator, group, events = instance(node_path, failure)
    with pytest.raises(OSError, match=failure):
        site.prepare(guard())
    assert site.state == "failed" and Path(site.plan.files.node_root).exists()
    before = list(events)
    with pytest.raises(RuntimeError):
        site.prepare(guard())
    with pytest.raises(RuntimeError):
        site.start(guard())
    assert events == before and group.names == []
    assert (site.port_lease is None) == (failure in ("files", "ports"))
    site.stop(guard())
    assert not allocator.lease.released
    assert Path(site.plan.files.node_root).exists()


@pytest.mark.parametrize("service", ["mysql", "redis", "search", "php", "nginx"])
def test_each_partial_start_stops_original_group_without_releasing_ports(
    node_path: Path, service: str
) -> None:
    site, allocator, group, _ = instance(node_path)
    site.prepare(guard())
    group.fail = service
    with pytest.raises(OSError):
        site.start(guard())
    original = tuple(group.names)
    with pytest.raises(RuntimeError):
        site.start(guard())
    facts = site.stop(guard())
    assert tuple(f.service for f in facts) == original
    assert not allocator.lease.released


def test_stop_before_prepare_blocks_new_acquisition(node_path: Path) -> None:
    site, _, group, events = instance(node_path)
    assert site.stop(guard()) == () and group.stop_calls == 0
    with pytest.raises(RuntimeError):
        site.prepare(guard())
    assert events == []
    assert not Path(site.plan.files.node_root).exists()


def test_cancel_before_prepare_has_no_effect_and_original_owner_can_prepare(
    node_path: Path,
) -> None:
    site, _, _, events = instance(node_path)
    with pytest.raises(TimeoutError):
        site.prepare(Stop(1))
    assert site.state == "new" and events == []
    site.prepare(guard())
    site.stop(guard())


def test_cancel_before_start_does_not_lose_prepared_handles(node_path: Path) -> None:
    site, allocator, group, _ = instance(node_path)
    site.prepare(guard())
    with pytest.raises(TimeoutError):
        site.start(Stop(1))
    assert site.state == "prepared" and not group.names
    site.stop(guard())
    assert not allocator.lease.released


def test_cleanup_error_keeps_original_error_handles_and_files(node_path: Path) -> None:
    site, allocator, group, _ = instance(node_path)
    site.prepare(guard())
    site.start(guard())
    error = BaseExceptionGroup(
        "master plus cleanup", [ValueError("primary"), OSError("cleanup")]
    )
    group.stop_error = error
    with pytest.raises(BaseExceptionGroup) as caught:
        site.stop(guard())
    assert (
        caught.value is error
        and getattr(error, "admin_instance_id") == site.plan.files.instance_id
    )
    assert site.state == "failed" and site.service_group is group
    assert site.services is not None and site.services.state == "failed"
    assert not allocator.lease.released and Path(site.plan.files.node_root).exists()


def test_unconfirmed_stop_is_not_promoted_to_stopped(node_path: Path) -> None:
    site, allocator, group, _ = instance(node_path)
    site.prepare(guard())
    site.start(guard())
    group.unconfirmed = True
    with pytest.raises(RuntimeError, match="unconfirmed"):
        site.stop(guard())
    assert site.stop_facts and all(f.state == "unconfirmed" for f in site.stop_facts)
    assert site.state == "failed" and not allocator.lease.released
    assert site.services is not None and site.services.state == "failed"


def test_cleanup_reaches_group_even_when_control_already_expired(
    node_path: Path,
) -> None:
    site, allocator, group, _ = instance(node_path)
    site.prepare(guard())
    with pytest.raises(TimeoutError):
        site.stop(Stop(1))
    assert group.stop_calls == 1 and not allocator.lease.released


def test_other_thread_cannot_prepare_or_stop(node_path: Path) -> None:
    site, _, _, events = instance(node_path)
    with ThreadPoolExecutor(max_workers=1) as executor:
        for method in (site.prepare, site.stop):
            future = executor.submit(method, guard())
            with pytest.raises(RuntimeError, match="original process/thread"):
                future.result(timeout=5)
    assert events == [] and site.state == "new"


def test_bootstrap_construction_and_invalid_apptainer_have_no_side_effect(
    node_path: Path,
) -> None:
    files = plan(node_path)
    with pytest.raises(ValueError):
        AdminInstancePlan(files=files, apptainer="relative")
    site = build_admin_instance(
        AdminInstancePlan(files=files, apptainer="/usr/bin/apptainer")
    )
    assert site.state == "new" and not Path(files.node_root).exists()
