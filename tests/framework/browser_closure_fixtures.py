"""Synthetic closure inputs collected from the original registered resource.

The capture below is explicitly synthetic; only installed tests establish real
kernel/controller facts. This fixture never signals a process or calls a site.
"""

from dataclasses import dataclass
from pathlib import Path
import json
import pytest
from browser_resource_fixtures import Authority, ResourceCase, resource_case
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceAttempt,
    BrowserResourceSpec,
)
from lab_generate_skill.domain.browser_step import BrowserStepClosed
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.lifecycle import ClosureReceipt, OperationContext
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from browser_worker_fixtures import configuration


def controlled_timeout_configuration(
    installation: ReleaseInstallation | None, job_id: str, url: str
) -> BrowserWorkerConfiguration:
    config = configuration(installation, url)
    scope = config.spec.scope.model_copy(
        update={"owner": config.spec.scope.owner.model_copy(update={"job_id": job_id})}
    )
    return BrowserWorkerConfiguration.model_validate(
        {
            **config.model_dump(),
            "spec": {
                **config.spec.model_dump(),
                "scope": scope,
                "action_timeout_ms": 10000,
            },
        }
    )


class RecordingAuthority(Authority):
    inputs: (
        tuple[
            BrowserResourceAttempt, ProcessTermination | None, BrowserStepClosed | None
        ]
        | None
    ) = None

    def verify_closed(
        self,
        spec: BrowserResourceSpec,
        attempt: BrowserResourceAttempt,
        termination: ProcessTermination | None,
        step: BrowserStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        self.inputs = (attempt, termination, step)
        return super().verify_closed(
            spec, attempt, termination, step, operation, control
        )


@dataclass
class ClosureCase:
    resource: ResourceCase
    attempt: BrowserResourceAttempt
    termination: ProcessTermination
    step: BrowserStepClosed

    def raw_step(self, **changes: object) -> BrowserStepClosed:
        raw: dict[str, object] = {
            "schema_version": "browser-step-raw/1",
            "phase": "closed",
            "target": self.step.target.model_dump(mode="json"),
            "kernel": [{"synthetic_unit_fixture": True}],
            "commands": [{"complete": True, "returncode": 0}],
            "error": None,
        }
        raw.update(changes)
        ref = self.resource.evidence.put(
            json.dumps(raw).encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="browser-step-raw/1",
                visibility="private",
                producer="synthetic-closure-fixture",
            ),
        )
        return self.step.model_copy(update={"evidence": ref})


@pytest.fixture
def closure_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ClosureCase:
    c = resource_case(tmp_path, monkeypatch)
    authority = RecordingAuthority(c.evidence)
    c.authority = authority
    with registered_browser(
        c.spec,
        c.op,
        journal=c.journal,
        evidence=c.evidence,
        controls=c.controls,
        clock=c.clock,
        authority=authority,
    ):
        pass
    assert authority.inputs is not None
    attempt, termination, step = authority.inputs
    assert termination is not None and step is not None and attempt.started is not None
    result = ClosureCase(c, attempt, termination, step)
    result.step = result.raw_step()
    return result
