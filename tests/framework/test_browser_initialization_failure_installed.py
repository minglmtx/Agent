"""Real failed initial navigation, original CPU worker/domain closure, no site."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.browsergym.worker_client import BrowserWorkerFailure
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from browser_resource_fixtures import resource_case
from browser_worker_fixtures import configuration
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from test_browser_resource_installed import EngineeringTreeAuthority
from test_linux_cgroups import actual_slurm_execution


def test_original_prepared_worker_closed_after_real_initial_navigation_failure(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, _ = actual_slurm_execution()
    # Keep the original port bound but not listening, so failure cannot contact
    # another process or depend on a guessed free port.
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        config = configuration(
            storage_installation(installed_sources),
            f"http://127.0.0.1:{reserved.getsockname()[1]}/",
        )
        config = config.model_copy(
            update={
                "spec": config.spec.model_copy(
                    update={
                        "scope": config.spec.scope.model_copy(
                            update={
                                "owner": config.spec.scope.owner.model_copy(
                                    update={"job_id": execution.job_id}
                                )
                            }
                        )
                    }
                )
            }
        )
        c = resource_case(tmp_path, monkeypatch, config=config, real_step=True)
        monkeypatch.setattr(
            "lab_generate_skill.adapters.browsergym.resource.FramedProcessSession",
            FramedProcessSession,
        )
        c.authority = EngineeringTreeAuthority(c.evidence)
        c.op = c.op.model_copy(
            update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=90)}
        )
        with pytest.raises(BrowserWorkerFailure) as caught:
            with registered_browser(
                c.spec,
                c.op,
                journal=c.journal,
                evidence=c.evidence,
                controls=c.controls,
                clock=c.clock,
                authority=c.authority,
            ):
                pytest.fail("Failed real navigation must not acquire a browser")
        record = c.journal.read(
            c.spec.token,
            c.op.cleanup("inspect-ended", now=datetime.now(timezone.utc), seconds=30),
        )
        assert [event.state for event in record.events] == [
            "registered",
            "acquiring",
            "acquired",
            "closing",
            "closed",
        ]
        ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))["details"]
        acquired = BrowserWorkerAcquiredFact.model_validate_json(
            c.evidence.read(record.events[2].evidence[0])
        )
        acquired.check_spec(c.spec)
        assert acquired.details.prepared_ref == EvidenceRef.model_validate(
            ending["attempt"]["prepared_ref"]
        )
        assert (
            acquired.details.prepared.model_dump(mode="json")
            == ending["attempt"]["prepared"]
        )
        assert ending["initial_ready_ref"] is None
        assert ending["attempt"]["prepared_ref"] is not None
        assert ending["attempt"]["started"] is None and ending["last_readout"] is None
        assert ending["step_closed"] is not None and not ending["cleanup_errors"]
        assert ending["primary"]["type_name"] == "BrowserWorkerFailure"
        assert ending["startup_reply"]["error"] is not None
        assert ending["configuration_reply"]["readout"] is None
        assert ending["process_stop"]["worker_exit_observed"] is True
        assert ending["process_stop"]["supervisor_exit_observed"] is True
        capture = EvidenceRef.model_validate(ending["worker_capture_ref"])
        assert json.loads(c.evidence.read(capture))["phase"] == "worker-capture"
        assert caught.value.reply.readout is None
        (
            Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
            / "browser-initialization-failure.json"
        ).write_text(
            json.dumps(
                {
                    "engineering_only": True,
                    "site_started": False,
                    "actor_calls": 0,
                    "paid_calls": 0,
                    "resource": record.model_dump(mode="json"),
                    "ending": ending,
                },
                indent=2,
            )
            + "\n"
        )
