"""Actual original CPU worker/store/guard; intentional rejection before DB I/O."""

import json
import errno
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
import pytest
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from gitlab_site_storage_live import missing_asset_configuration
from site_resource_fixtures import resource_case
from test_site_resource_installed import EngineeringAuthority
from test_site_resource import enter, inspect
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from test_linux_cgroups import actual_slurm_execution


def test_original_gitlab_cpu_worker_initializes_private_storage_before_asset_rejection(
    installed_sources: InstalledFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, _ = actual_slurm_execution()
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    root = output / "original-gitlab-storage"
    root.mkdir(mode=0o700)
    (root / "sessions").mkdir(mode=0o700)
    parent = Path(tempfile.mkdtemp(prefix="lab-gitlab-storage-", dir="/tmp"))
    config = missing_asset_configuration(
        storage_installation(installed_sources),
        job_id=execution.job_id,
        root=root,
        parent=parent,
    )
    c = resource_case(root, monkeypatch, config=config, real_step=True)
    authority = EngineeringAuthority(c, parent)
    c.authority = authority
    facts: dict[str, Any] = dict(
        passed=False,
        engineering_only=True,
        actual_original_cpu_worker=True,
        actual_storage_worker=False,
        native_db_started=False,
        actor_calls=0,
        paid_calls=0,
        private_root=str(parent),
    )
    try:
        with pytest.raises(SiteWorkerFailure) as caught:
            with enter(c):
                pytest.fail(
                    "Missing selected image must not yield a usable GitLab site"
                )
        reply = caught.value.reply
        facts["original_startup_reply"] = reply.model_dump(mode="json")
        assert reply.error is not None and reply.error.type_name == "FileNotFoundError"
        assert reply.started is None and reply.exits == ()
        assert reply.error.errno == errno.ENOENT
        assert any(
            f.function == "stage" and f.filename.endswith("/sites/files.py")
            for f in reply.error.frames
        )
        assert not Path(config.files.node_root).exists()
        plan = c.spec.configuration.private_evidence
        assert plan is not None
        session = EvidenceSessionSnapshot.model_validate_json(
            (
                Path(plan.config.session_root)
                / (plan.binding.namespace_key + ".evidence-session.json")
            ).read_bytes()
        )
        assert (
            session.binding == plan.binding and session.capacity == plan.config.capacity
        )
        assert session.revision == 0 and session.entries == ()
        record = inspect(c)
        assert (
            record.state == "closed"
            and authority.before_native
            and authority.closed is not None
        )
        assert [e.state for e in record.events] == [
            "registered",
            "acquiring",
            "acquired",
            "closing",
            "closed",
        ]
        ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))
        assert ending["details"]["cleanup_errors"] == []
        capture = json.loads(
            c.evidence.read(
                EvidenceRef.model_validate(ending["details"]["worker_capture_ref"])
            )
        )
        facts.update(
            passed=True,
            actual_storage_worker=True,
            original_configuration=c.spec.configuration.model_dump(mode="json"),
            expected_startup_error=reply.model_dump(mode="json"),
            initialized_session=session.model_dump(mode="json"),
            record=record.model_dump(mode="json"),
            original_domain=authority.closed.model_dump(mode="json"),
            worker_capture=capture,
        )
    except BaseException as error:
        facts["error"] = describe_error(error).model_dump(mode="json")
        raise
    finally:
        record = inspect(c)
        facts["final_record"] = record.model_dump(mode="json")
        if record.state == "closed":
            ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))
            facts["final_ending"] = ending
            facts["original_worker_capture"] = json.loads(
                c.evidence.read(
                    EvidenceRef.model_validate(ending["details"]["worker_capture_ref"])
                )
            )
        if facts["passed"] and authority.closed is not None:
            assert parent.resolve(strict=True) == parent and not parent.is_symlink()
            shutil.rmtree(parent)
        facts["private_root_removed"] = not parent.exists()
        (output / "gitlab-original-worker-storage.json").write_text(
            json.dumps(facts, indent=2) + "\n"
        )
