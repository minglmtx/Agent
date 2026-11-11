"""Actual installed CPU worker; source denial prevents all native site effects.

Original permissions remain explicit engineering fixtures. This proves independent
original Slurm ownership/closure, not a formal source, browser or business result.
"""

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Literal
import pytest
from lab_generate_skill.adapters.sites.physical_authority import (
    ObservedSiteResourceAuthority,
)
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.ports.lifecycle import OperationControl
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from site_resource_fixtures import Authority, resource_case
from site_worker_fixtures import configuration
from test_linux_cgroups import actual_slurm_execution
from test_site_resource import inspect


class DenyNativeStart(Authority):
    def verify(
        self,
        configuration: SiteWorkerConfiguration,
        phase: Literal["configure", "start", "close"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        super().verify(configuration, phase, operation, control)
        if phase == "start":
            raise PermissionError("Original engineering source forbids native start")


def test_installed_original_cpu_worker_configuration_denial_and_independent_close(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, _ = actual_slurm_execution()
    parent = Path(tempfile.mkdtemp(prefix="lab-site-authority-", dir="/tmp"))
    base = configuration(
        storage_installation(installed_sources), job_id=execution.job_id
    )
    config = base.model_copy(
        update={
            "files": base.files.model_copy(
                update={"node_root": str(parent / "instance")}
            )
        }
    )
    c = resource_case(tmp_path, monkeypatch, config=config, real_step=True)
    source = DenyNativeStart(c.evidence)
    authority = ObservedSiteResourceAuthority(
        c.spec, c.op, source=source, evidence=c.evidence
    )
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    facts: dict[str, object] = {
        "passed": False,
        "formal_source": False,
        "native_site_started": False,
        "business_requests": 0,
    }
    try:
        with authority:
            with pytest.raises(PermissionError, match="forbids native start"):
                with registered_site(
                    c.spec,
                    c.op,
                    journal=c.journal,
                    evidence=c.evidence,
                    controls=c.controls,
                    clock=c.clock,
                    authority=authority,
                ):
                    pytest.fail("native effects were not admitted")
        assert authority.ready is not None and authority.closed is not None
        assert authority.ready.controller.target == authority.closed.target
        assert authority.ready.controller.gpu_type is None
        assert inspect(c).state == "closed" and source.close_calls == 1
        assert not Path(config.files.node_root).exists()
        assert authority._state.pin is None and authority._state.processes is None
        facts.update(
            passed=True,
            original_ready=authority.ready.model_dump(mode="json"),
            independent_closed=authority.closed.model_dump(mode="json"),
            observations=[r.model_dump(mode="json") for r in authority.observations],
            record=inspect(c).model_dump(mode="json"),
            source_calls=source.calls,
            native_root_created=False,
        )
    finally:
        facts["observations"] = [
            r.model_dump(mode="json") for r in authority.observations
        ]
        shutil.copytree(tmp_path, output / "site-authority-original-evidence")
        (output / "site-authority-installed-facts.json").write_text(
            json.dumps(facts, indent=2) + "\n"
        )
        if authority.closed is not None and not any(parent.iterdir()):
            parent.rmdir()


def test_installed_original_close_observation_survives_unusable_store_without_clean_ledger(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typing import Any
    from lab_generate_skill.domain.errors import InvalidTransition
    from test_initialization_storage_cleanup import failures

    execution, _ = actual_slurm_execution()
    parent = Path(tempfile.mkdtemp(prefix="lab-site-storage-loss-", dir="/tmp"))
    base = configuration(
        storage_installation(installed_sources), job_id=execution.job_id
    )
    config = base.model_copy(
        update={
            "files": base.files.model_copy(
                update={"node_root": str(parent / "instance")}
            )
        }
    )
    c = resource_case(tmp_path, monkeypatch, config=config, real_step=True)
    source = DenyNativeStart(c.evidence)
    authority = ObservedSiteResourceAuthority(
        c.spec, c.op, source=source, evidence=c.evidence
    )
    original_verify = source.verify

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise InvalidTransition("Original storage instance is not ready")

    def verify(*args: Any, **kwargs: Any) -> Any:
        try:
            return original_verify(*args, **kwargs)
        except PermissionError:
            monkeypatch.setattr(c.evidence, "put", unavailable)
            monkeypatch.setattr(c.evidence, "read", unavailable)
            raise

    monkeypatch.setattr(source, "verify", verify)
    try:
        with pytest.raises(BaseExceptionGroup) as caught:
            with authority:
                with registered_site(
                    c.spec,
                    c.op,
                    journal=c.journal,
                    evidence=c.evidence,
                    controls=c.controls,
                    clock=c.clock,
                    authority=authority,
                ):
                    pytest.fail("Original native start denial was bypassed")
        errors = failures(caught.value)
        assert any(
            isinstance(e, PermissionError) and "forbids native start" in str(e)
            for e in errors
        )
        assert any(isinstance(e, InvalidTransition) for e in errors)
        observations = [
            getattr(e, "site_resource_physical_observation")
            for e in errors
            if hasattr(e, "site_resource_physical_observation")
        ]
        assert observations
        observed = observations[0]
        assert (
            observed["target"] is not None
            and observed["termination"]["state"] == "reaped"
        )
        assert observed["quiescence"] is not None
        assert (
            not observed["step_closure_evidence_returned"]
            and not observed["durable_resource_close_confirmed"]
        )
        assert (
            authority.closed is None
            and authority._state.pin is None
            and authority._state.processes is None
        )
        assert not Path(config.files.node_root).exists()
        assert inspect(c).state == "acquired"
        (
            Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
            / "site-storage-loss-original-close.json"
        ).write_text(
            json.dumps(
                {
                    "physical_observation": observed,
                    "durable_close_confirmed": False,
                    "safe_Reset_or_runtime_source_granted": False,
                    "native_site_started": False,
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        if not any(parent.iterdir()):
            parent.rmdir()
