"""Use actual record stores and a synthetic browser to exercise initial-check I/O."""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.bootstrap.admin_navigation import (
    admin_navigation_initial_observations,
)
from lab_generate_skill.domain.initial_observation import (
    InitialObservationInputs,
    InitialObservationSelection,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.ports.lifecycle import OperationControl
from admin_navigation_prepared_fixtures import prepared_case, Case as PreparedCase
from typing import Any
from lab_generate_skill.sites.shopping_admin.tasks.navigation_initial_observation import (
    NAVIGATION_INITIAL_CHECKS,
)


class Authority:
    def __init__(self, selection: InitialObservationSelection) -> None:
        self.selection, self.calls, self.denied = selection, 0, False

    def verify(
        self,
        inputs: InitialObservationInputs,
        checks: StateChecks,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert inputs.selection == self.selection
        self.calls += 1
        if self.denied:
            raise PermissionError("Initial-check permission denied")


@dataclass
class Case:
    prepared: PreparedCase
    selection: InitialObservationSelection
    records: EvidenceInitialObservations
    authority: Authority
    op: OperationContext
    session: EvidenceBrowserSession


@contextmanager
def initial_case(
    root: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> Iterator[Case]:
    with prepared_case(
        root, monkeypatch, contracts=contracts, initial_checks=NAVIGATION_INITIAL_CHECKS
    ) as c:
        b = c.browser
        with registered_browser(
            b.spec,
            b.op,
            journal=b.journal,
            evidence=b.evidence,
            controls=b.controls,
            clock=b.clock,
            authority=c.authority,
        ) as session:
            record = b.journal.read(b.spec.token, b.op)
            intent = ResourceAcquisitionIntent.model_validate_json(
                b.evidence.read(record.events[1].evidence[0])
            )
            assert session.resource_started_ref is not None
            selection = InitialObservationSelection(
                preparation=c.binding.publication,
                browser_spec_ref=intent.configuration_ref,
                browser_acquired_ref=session.resource_started_ref,
            )
            authority = Authority(selection)
            records = admin_navigation_initial_observations(
                b.evidence, b.controls, c.preparation.adapter, authority
            )
            yield Case(
                c,
                selection,
                records,
                authority,
                b.op.model_copy(update={"operation_id": "initial-checks"}),
                session,
            )
