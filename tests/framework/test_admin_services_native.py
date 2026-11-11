"""Actual pinned-image Admin instance through production assembly, no admission."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import time
from typing import Any
from collections.abc import Callable
import urllib.request
from lab_generate_skill.bootstrap.admin_instance import build_admin_instance
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.adapters.network.loopback_ports import (
    LoopbackPorts,
    PortsUnavailable,
)
from lab_generate_skill.sites.shopping_admin.instance_contract import AdminInstancePlan
from lab_generate_skill.sites.shopping_admin.instance import AdminInstance
from lab_generate_skill.sites.shopping_admin.service_contract import AdminServiceSpec
from lab_generate_skill.sites.shopping_admin.service_commands import container
from test_admin_database_native import IMAGE, IMAGE_SHA
from test_slurm_commands import guard
from native_probe_evidence import preserve_failure


def assert_reserved(ports: tuple[int, ...]) -> None:
    try:
        unexpected = LoopbackPorts(candidates=ports).reserve(1, guard(5))
    except PortsUnavailable:
        return
    unexpected.release(guard(5))
    raise AssertionError("A concurrent allocator bypassed the held port lease")


def run_admin_services_probe(
    probe: Callable[[AdminServiceSpec, NativeCommands], dict[str, Any]] | None = None,
    *,
    programs: tuple[str, ...] = (),
    instance_probe: Callable[[AdminInstance], dict[str, Any]] | None = None,
) -> None:
    assert probe is None or instance_probe is None
    assert os.environ.get("SLURM_JOB_ID")
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    parent = Path(tempfile.mkdtemp(prefix="lab-admin-instance-", dir="/tmp"))
    root = parent / "instance"
    plan = AdminInstancePlan(
        files=SiteFilesPlan(
            instance_id="services-" + os.environ["SLURM_JOB_ID"],
            workspace_root="/anvme/workspace/r102bf10-lab-generate-skill",
            source_path=str(IMAGE),
            node_root=str(root),
            image=ReleaseFile(
                path=IMAGE.name,
                sha256=IMAGE_SHA,
                size_bytes=1356492800,
                executable=False,
            ),
        ),
        apptainer="/usr/bin/apptainer",
    )
    site = build_admin_instance(plan)
    commands = site.commands
    state, logs = Path(plan.files.state_root), Path(plan.files.log_root)
    facts: dict[str, Any] = dict(
        passed=False,
        engineering_only=True,
        task_initialized=False,
        private_root=str(root),
        image_sha256=IMAGE_SHA,
        whole_resource_closure_verified=False,
        assembly_plan=plan.model_dump(mode="json"),
    )
    original: BaseException | None = None
    began = time.monotonic()
    clean = False
    ports: tuple[int, ...] = ()
    try:
        spec = site.prepare(guard(120))
        facts["image_and_seed_prepare_seconds"] = time.monotonic() - began
        assert site.port_lease is not None
        ports = site.port_lease.ports
        assert_reserved(ports)
        facts["ports_exclusive_before_start"] = True
        # Production assembly already linted its fixed programs before extraction.
        # Any extra task probe programs are checked before service startup here.
        for program in programs:
            commands.run(
                container(spec) + ("php", "-r", "if(false){" + program + "}"), guard(20)
            )
        facts["native_program_syntax_checked"] = True
        starting = time.monotonic()
        url = site.start(guard(150))
        facts["startup_seconds"] = time.monotonic() - starting
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=10) as response:
            body = response.read(2 * 1024 * 1024 + 1)
            assert response.status == 200 and len(body) <= 2 * 1024 * 1024
            assert b"login" in body.lower() or b"sign in" in body.lower()
            assert response.url.startswith(f"http://127.0.0.1:{ports[0]}/")
            facts["login"] = dict(
                status=response.status,
                url=response.url,
                bytes=len(body),
                sha256=hashlib.sha256(body).hexdigest(),
            )
        assert site.service_group is not None
        site.service_group.require_running()
        facts["ports"] = ports
        assert_reserved(ports)
        facts["ports_exclusive_while_running"] = True
        if probe is not None:
            facts["product_probe"] = probe(spec, commands)
        if instance_probe is not None:
            facts["instance_probe"] = instance_probe(site)
        facts["passed"] = True
    except BaseException as error:
        original = error
        facts["error_type"] = type(error).__name__
        facts["error"] = str(error)
        try:
            facts["failure_evidence"] = preserve_failure(output, error)
        except BaseException as diagnostic_error:
            facts["diagnostic_error"] = repr(diagnostic_error)
            error.add_note(
                "Failed to persist native diagnostics: " + repr(diagnostic_error)
            )
        raise
    finally:
        cleanup: BaseException | None = None
        try:
            exits = site.stop(guard(20))
            facts["master_exits"] = [item.model_dump(mode="json") for item in exits]
            facts["service_names"] = [item.service for item in exits]
            clean = all(item.state == "reaped" for item in exits)
            assert clean
            if facts["passed"]:
                expected_names = [
                    "mysql",
                    "redis",
                    "search",
                    "php",
                    "nginx",
                ]
                if site.frontend_recovery is not None:
                    expected_names += ["php-restored", "nginx-restored"]
                assert facts["service_names"] == expected_names
            bound = []
            for port in ports:
                with socket.socket() as sock:
                    sock.settimeout(0.2)
                    if sock.connect_ex(("127.0.0.1", port)) == 0:
                        bound.append(port)
            facts["ports_still_listening"] = bound
            assert not bound
            # stop never drops the lock; outer engineering owner verifies above.
            if site.port_lease is not None:
                assert_reserved(site.port_lease.ports)
                facts["ports_retained_after_stop"] = True
                site.port_lease.release(guard(5))
                facts["port_lease_released_after_stop"] = True
        except BaseException as error:
            cleanup = error
            clean = False
            facts["passed"] = False
            facts["cleanup_error_type"] = type(error).__name__
            facts["cleanup_error"] = str(error)
        finally:
            facts["seconds"] = time.monotonic() - began
            facts["private_root_removed"] = False
            for log in [*logs.glob("*.log"), *state.glob("*.log")]:
                shutil.copyfile(log, output / ("admin-services-" + log.name))
            if clean and facts["passed"]:
                shutil.rmtree(parent)
                facts["private_root_removed"] = True
            (output / "admin-services-native.json").write_text(
                json.dumps(facts, indent=2) + "\n"
            )
        if cleanup is not None:
            raise BaseExceptionGroup(
                "Native site check and cleanup failed",
                ([original] if original else []) + [cleanup],
            ) from None


def test_real_admin_services_reach_login_and_stop_original_masters() -> None:
    run_admin_services_probe()
