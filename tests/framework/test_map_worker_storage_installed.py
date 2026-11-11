"""Actual Map worker/resource/file authority; reject before native input I/O.

This checks the new installation/dispatch and actual kernel ownership boundary,
not a running Map website, formal source authority or an Actor result.
"""

import errno
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
import pytest
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from map_worker_storage_live import missing_input_configuration
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


def test_original_map_worker_initializes_files_then_rejects_missing_publication(
    installed_sources: InstalledFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, _ = actual_slurm_execution()
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    root = output / "original-map-storage"
    root.mkdir(mode=0o700)
    parent = Path(tempfile.mkdtemp(prefix="lab-map-storage-", dir="/tmp"))
    cfg = missing_input_configuration(
        storage_installation(installed_sources),
        job_id=execution.job_id,
        root=root,
        parent=parent,
    )
    c = resource_case(root, monkeypatch, config=cfg, real_step=True)
    authority = EngineeringAuthority(c, parent)
    c.authority = authority
    facts: dict[str, Any] = dict(
        passed=False,
        engineering_only=True,
        actual_original_cpu_worker=True,
        native_services_started=False,
        actor_calls=0,
        paid_calls=0,
        private_root=str(parent),
        original_configuration=c.spec.configuration.model_dump(mode="json"),
    )
    try:
        with pytest.raises(SiteWorkerFailure) as caught:
            with enter(c):
                pytest.fail("Missing publication must not yield a usable Map site")
        reply = caught.value.reply
        facts["original_startup_reply"] = reply.model_dump(mode="json")
        assert reply.error is not None and reply.error.type_name == "FileNotFoundError"
        assert reply.error.errno == errno.ENOENT
        assert reply.started is None and reply.exits == ()
        assert any(
            f.function == "read_pinned_bytes"
            and f.filename.endswith("/map_runtime/metadata.py")
            for f in reply.error.frames
        )
        assert not Path(cfg.files.node_root).exists()
        assert cfg.map_inputs is not None
        artifact_root = Path(cfg.map_inputs.artifact_root)
        st = artifact_root.lstat()
        assert artifact_root.is_dir() and not artifact_root.is_symlink()
        assert st.st_uid == os.getuid() and st.st_mode & 0o777 == 0o700
        assert not list(artifact_root.iterdir())
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
        with pytest.raises(DispatchAlreadyCommitted):
            with enter(c):
                pytest.fail("Original resource cannot launch again")
        assert artifact_root.stat().st_ino == st.st_ino and not list(
            artifact_root.iterdir()
        )
        facts.update(
            passed=True,
            actual_original_file_authority=True,
            initialized_artifact_root=str(artifact_root),
            artifact_root_mode=oct(st.st_mode & 0o777),
            record=record.model_dump(mode="json"),
            original_domain=authority.closed.model_dump(mode="json"),
            duplicate_launch_rejected=True,
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
        (output / "map-original-worker-storage.json").write_text(
            json.dumps(facts, indent=2) + "\n"
        )
