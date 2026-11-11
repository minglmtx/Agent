"""Real Shopping services, native fixture, coherent restore; not an Actor task."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any
from lab_generate_skill.bootstrap.shopping_instance import build_shopping_instance
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from lab_generate_skill.adapters.browsergym.login_catalog import shopping_login
from lab_generate_skill.sites.shopping.service_commands import container
from lab_generate_skill.sites.shopping.tasks.order_eta_programs import (
    RECORDED_ETA,
    PROTECTION,
)
from test_slurm_commands import guard
from shopping_native_diagnostics import retain_native_failure

WORKSPACE = Path("/anvme/workspace/r102bf10-lab-generate-skill")
IMAGE_SHA = "455ec7d98aa89b7b63b627aea567f91816d75da50bd160f5db2cc1dfe52f6812"
IMAGE = WORKSPACE / "assets/webarena/shopping" / IMAGE_SHA / "shopping.sif"


def test_actual_shopping_original_snapshot_native_comment_and_complete_restore() -> (
    None
):
    assert os.environ.get("SLURM_JOB_ID")
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "shopping-native"
    output.mkdir(mode=0o700)
    parent = Path(tempfile.mkdtemp(prefix="lab-shopping-native-", dir="/tmp"))
    plan = SiteFilesPlan(
        instance_id="shopping-" + os.environ["SLURM_JOB_ID"],
        workspace_root=str(WORKSPACE),
        source_path=str(IMAGE),
        node_root=str(parent / "instance"),
        image=ReleaseFile(
            path=IMAGE.name, size_bytes=43470442496, sha256=IMAGE_SHA, executable=False
        ),
    )
    instance = build_shopping_instance(plan)
    facts: dict[str, Any] = {
        "engineering_only": True,
        "actor_calls": 0,
        "paid_calls": 0,
        "actual_browser_login": False,
        "passed": False,
        "node_root": plan.node_root,
        "image_sha256": IMAGE_SHA,
        "phases": [],
        "cleanup_errors": [],
    }
    started = time.monotonic()
    primary: BaseException | None = None

    def phase(name: str) -> None:
        facts["phases"].append(
            {"phase": name, "elapsed_seconds": time.monotonic() - started}
        )
        with (output / "progress.jsonl").open("a") as stream:
            stream.write(json.dumps(facts["phases"][-1]) + "\n")

    def retain(name: str, raw: bytes) -> None:
        path = output / (name + ".json")
        with path.open("xb") as stream:
            stream.write(raw)
        path.chmod(0o600)
        facts[name + "_sha256"] = hashlib.sha256(raw).hexdigest()

    try:
        retain("declared_instance", plan.model_dump_json().encode())
        phase("prepare_begin")
        spec = instance.prepare(guard(1200))
        phase("prepared")
        endpoint = instance.start(guard(300))
        facts["endpoint"] = endpoint
        phase("original_ready")
        base = container(spec)
        before_raw = instance.commands.run(base + ("php", "-r", PROTECTION), guard(120))
        retain("original_protection", before_raw)
        before = json.loads(before_raw)
        phase("snapshot_begin")
        snapshot = instance.snapshot_and_restart(guard(600))
        retain("snapshot", snapshot.model_dump_json().encode())
        phase("snapshot_and_original_endpoint_ready")
        restarted_raw = instance.commands.run(
            base + ("php", "-r", PROTECTION), guard(120)
        )
        assert json.loads(restarted_raw) == before
        retain("restarted_protection", restarted_raw)
        email, _password = shopping_login(guard(10))
        parameters = json.dumps(
            {
                "operation": "initialize",
                "email": email,
                "order_number": "000000148",
                "date": "2023-02-03",
            }
        )
        initialized_raw = instance.commands.run(
            base + ("php", "-r", RECORDED_ETA, parameters), guard(120)
        )
        retain("native_fixture", initialized_raw)
        initialized = json.loads(initialized_raw)
        assert (
            initialized["order_number"],
            initialized["date"],
            initialized["external_delivery"],
        ) == ("000000148", "2023-02-03", False)
        after_raw = instance.commands.run(base + ("php", "-r", PROTECTION), guard(120))
        retain("prepared_protection", after_raw)
        after = json.loads(after_raw)
        changed = [
            name
            for name in before["tables"]
            if before["tables"][name] != after["tables"][name]
        ]
        assert changed == ["sales_order_status_history"]
        assert (
            after["tables"][changed[0]]["rows"]
            == before["tables"][changed[0]]["rows"] + 1
        )
        facts["native_fixture_changed_tables"] = changed
        # Controlled state mutations exercise the same complete snapshot; this
        # is recovery validation, not a claimed Actor/website action.
        instance.commands.run(
            base
            + (
                "php",
                "-r",
                "file_put_contents('/state/uploads/recovery-probe','upload');file_put_contents('/state/mail-outbox/recovery-probe.eml','local-only');",
            ),
            guard(10),
        )
        phase("native_fixture_and_mutations_verified")
        restored = instance.restore(snapshot, guard(300))
        assert restored == snapshot.inventory
        assert not (Path(plan.state_root) / "uploads/recovery-probe").exists()
        assert not (Path(plan.state_root) / "mail-outbox/recovery-probe.eml").exists()
        phase("full_tree_restored")
        assert instance.resume(guard(300)) == endpoint
        final_raw = instance.commands.run(base + ("php", "-r", PROTECTION), guard(120))
        retain("restored_protection", final_raw)
        assert json.loads(final_raw) == before
        facts["all_protected_native_rows_restored"] = True
        phase("original_endpoint_and_native_state_restored")
        facts["passed"] = True
    except BaseException as error:
        primary = error
        facts["primary_error_type"] = type(error).__name__
        try:
            retained = retain_native_failure(output, error)
            facts["primary_native_capture"] = str(retained) if retained else None
        except BaseException as diagnostic:
            facts["cleanup_errors"].append(
                type(diagnostic).__name__ + ": " + str(diagnostic)
            )
    finally:
        # Retain original init/launcher facts before closing any namespace fd.
        for generation in reversed(instance.generations):
            group = generation.services
            assert isinstance(group, LocalNativeServices)
            try:
                if set(group.namespaces) != set(group.children):
                    raise RuntimeError(
                        "Unpinned partial native children; retain private root"
                    )
                if not group.stopping:
                    for name in tuple(group.namespaces):
                        group.stop_namespace(name, guard(20))
                if any(x.stopped is None for x in group.namespaces.values()):
                    raise RuntimeError("Original native namespace remains unconfirmed")
            except BaseException as cleanup:
                facts["cleanup_errors"].append(
                    type(cleanup).__name__ + ": " + str(cleanup)
                )
        try:
            instance.stop(guard(60))
        except BaseException as cleanup:
            facts["cleanup_errors"].append(type(cleanup).__name__ + ": " + str(cleanup))
        facts["generations"] = []
        for generation in instance.generations:
            group = generation.services
            assert isinstance(group, LocalNativeServices)
            facts["generations"].append(
                {
                    "state": generation.state,
                    "quiescence": (
                        group.quiescence.model_dump(mode="json")
                        if group.quiescence
                        else None
                    ),
                    "namespace_stops": [
                        h.stopped.model_dump(mode="json") if h.stopped else None
                        for h in group.namespaces.values()
                    ],
                    "masters": [
                        x.model_dump(mode="json") for x in group.observations()
                    ],
                }
            )
        # Slurm may give subsequent jobs a different /tmp view. Persist original
        # diagnostics even after failure, before this job's namespace vanishes.
        try:
            if Path(plan.log_root).is_dir():
                shutil.copytree(plan.log_root, output / "service-logs")
            runtime = Path(plan.node_root) / "runtime"
            diagnostics = output / "runtime-logs"
            diagnostics.mkdir(mode=0o700)
            for path in runtime.glob("*.log"):
                if path.is_symlink() or not path.is_file():
                    raise ValueError("Unexpected original runtime diagnostic entry")
                shutil.copyfile(path, diagnostics / path.name)
        except BaseException as diagnostic:
            facts["cleanup_errors"].append(
                type(diagnostic).__name__ + ": " + str(diagnostic)
            )
        if facts["passed"] and not facts["cleanup_errors"]:
            try:
                if instance.lease is not None:
                    instance.lease.release(guard(10))
                shutil.rmtree(parent)
            except BaseException as cleanup:
                facts["cleanup_errors"].append(
                    type(cleanup).__name__ + ": " + str(cleanup)
                )
        facts["private_root_removed"] = not parent.exists()
        facts["elapsed_seconds"] = time.monotonic() - started
        with (output / "facts.json").open("x") as stream:
            json.dump(facts, stream, indent=2)
    if primary is not None:
        raise primary
    assert (
        facts["passed"]
        and not facts["cleanup_errors"]
        and facts["private_root_removed"]
    )
