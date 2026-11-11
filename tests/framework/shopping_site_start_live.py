"""Original failed installed startup only: one CPU worker, no Qwen or task replay."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import os
import shutil
import tempfile
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from site_resource_native_plan import native_configuration, startup_seconds
from site_resource_fixtures import resource_case
from test_site_resource_installed import EngineeringAuthority
from test_site_resource import inspect
from test_linux_cgroups import actual_slurm_execution
from storage_installation_fixtures import storage_installation
from shopping_native_diagnostics import retain_startup_logs
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_original_one_cpu_registered_shopping_startup(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, _ = actual_slurm_execution()
    output = (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "shopping-registered-startup"
    )
    output.mkdir(mode=0o700)
    parent = Path(tempfile.mkdtemp(prefix="lab-shopping-startup-", dir="/tmp"))
    config = native_configuration(
        storage_installation(installed_sources),
        job_id=execution.job_id,
        parent=parent,
        site_id="shopping",
    )
    c = resource_case(tmp_path, monkeypatch, config=config, real_step=True)
    seconds = startup_seconds("shopping")
    c.op = c.op.model_copy(
        update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=seconds)}
    )
    authority = EngineeringAuthority(c, parent)
    facts: dict[str, Any] = dict(
        engineering_only=True,
        passed=False,
        actor_calls=0,
        browser_calls=0,
        paid_calls=0,
        private_root=str(parent),
        startup_seconds=seconds,
    )
    (output / "declared-instance.json").write_text(c.spec.model_dump_json() + "\n")
    failure: BaseException | None = None
    try:
        try:
            with registered_site(
                c.spec,
                c.op,
                journal=c.journal,
                evidence=c.evidence,
                controls=c.controls,
                clock=c.clock,
                authority=authority,
            ) as site:
                assert site.site.instance.files == c.spec.configuration.files
                facts["started"] = site.site.model_dump(mode="json")
                facts["passed"] = True
        except BaseException as error:
            failure = error
            facts["passed"] = False
            facts["primary"] = describe_error(error).model_dump(mode="json")
        try:
            record = inspect(c)
            facts["resource_record"] = record.model_dump(mode="json")
            ending = json.loads(
                c.evidence.read(record.events[-1].evidence[0], guard(10))
            )
            facts["ending"] = ending
            capture_ref = ending["details"].get("worker_capture_ref")
            if capture_ref:
                from lab_generate_skill.domain.evidence import EvidenceRef

                (output / "original-worker-capture.json").write_bytes(
                    c.evidence.read(EvidenceRef.model_validate(capture_ref), guard(10))
                )
            assert record.state == "closed" and authority.closed is not None
            facts["startup_logs"] = retain_startup_logs(
                c.spec.configuration.files, output
            )
            if failure is None:
                assert (
                    not ending["details"]["cleanup_errors"]
                    and ending["details"]["primary"] is None
                )
                shutil.rmtree(parent)
        except BaseException as diagnostic:
            facts["passed"] = False
            facts["diagnostic_error"] = describe_error(diagnostic).model_dump(
                mode="json"
            )
            failure = (
                BaseExceptionGroup(
                    "Original startup and diagnostics failed", [failure, diagnostic]
                )
                if failure is not None
                else diagnostic
            )
    finally:
        facts["private_root_removed"] = not parent.exists()
        (output / "facts.json").write_text(json.dumps(facts, indent=2) + "\n")
    if failure is not None:
        raise failure
