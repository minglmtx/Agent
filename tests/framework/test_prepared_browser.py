"""Preparation/site/browser joining: exact originals, failures before spawn, cleanup."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    EvidenceNotFound,
)
from lab_generate_skill.domain.browser_initialization import (
    AdminProductInitialization,
    PublicNavigation,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from prepared_browser_fixtures import prepared_case
from test_slurm_commands import guard
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourceStarted,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.ports.lifecycle import OperationControl
from preparation_record_fixtures import put


def test_actual_record_graph_is_loaded_without_reprepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with prepared_case(tmp_path, monkeypatch) as c:
        b = c.browser
        before = c.preparation.authority.calls
        with registered_browser(
            b.spec,
            b.op,
            journal=b.journal,
            evidence=b.evidence,
            controls=b.controls,
            clock=b.clock,
            authority=c.authority,
        ) as session:
            assert session.observation_ref is not None
            assert b.channels[0].engine.last_readout is not None
            assert b.channels[0].engine.last_readout.observation.sequence == 0
        assert c.preparation.authority.calls == before + 4
        assert b.channels[0].engine.calls == ["start", "close"]
        assert b.journal.read(b.spec.token, b.op).state == "closed"
        assert c.site.journal.read(c.site.spec.token, c.site.op).state == "acquired"
        assert c.preparation.environment.checks.status == "unknown"


@pytest.mark.parametrize(
    "change", ["selection", "prepared", "context", "task", "site", "installation"]
)
def test_changed_binding_rejected_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    with prepared_case(tmp_path, monkeypatch) as c:
        b = c.browser
        config = b.spec.configuration
        selected = config.initialization
        assert isinstance(selected, AdminProductInitialization)
        if change == "selection":
            config = config.model_copy(update={"initialization": PublicNavigation()})
        elif change == "prepared":
            config = config.model_copy(
                update={
                    "initialization": selected.model_copy(
                        update={
                            "prepared_ref": selected.prepared_ref.model_copy(
                                update={"producer": "other"}
                            )
                        }
                    )
                }
            )
        elif change == "context":
            config = config.model_copy(
                update={
                    "spec": config.spec.model_copy(
                        update={
                            "scope": config.spec.scope.model_copy(
                                update={"context_id": "other"}
                            )
                        }
                    )
                }
            )
        elif change == "task":
            config = config.model_copy(
                update={
                    "spec": config.spec.model_copy(
                        update={
                            "task": config.spec.task.model_copy(
                                update={"goal": "different"}
                            )
                        }
                    )
                }
            )
        elif change == "site":
            c.binding.site = c.binding.site.model_copy(
                update={
                    "instance": c.binding.site.instance.model_copy(
                        update={
                            "endpoint": "http://127.0.0.1:23456/admin",
                            "ports": (23456,),
                        }
                    )
                }
            )
        else:
            config = config.model_copy(
                update={
                    "installation": config.installation.model_copy(
                        update={"python_executable": "/other/python"}
                    )
                }
            )
        changed = b.spec.model_copy(
            update={
                "configuration": BrowserWorkerConfiguration.model_validate(
                    config.model_dump()
                )
            }
        )
        with pytest.raises(OwnershipConflict):
            c.binding.verify(changed, b.op, guard())
        assert not b.channels


@pytest.mark.parametrize(
    "dependency", ["request_ref", "result_ref", "prepared_ref", "site_ref"]
)
@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_original_dependency_fault_prevents_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dependency: str, fault: str
) -> None:
    with prepared_case(tmp_path, monkeypatch) as c:
        pub = c.binding.publication
        if dependency == "site_ref":
            selected = c.browser.spec.configuration.initialization
            assert isinstance(selected, AdminProductInitialization)
            ref = selected.site_ref
        else:
            ref = getattr(
                pub if dependency == "prepared_ref" else pub.selection, dependency
            )
        path = tmp_path / "site/evidence/blobs" / ref.sha256
        if fault == "missing":
            path.unlink()
        else:
            path.write_bytes(b"corrupt")
        with pytest.raises(
            EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
        ):
            c.authority.authorize_start(c.browser.spec, c.browser.op, guard())
        assert not c.browser.channels


def test_denied_preparation_never_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with prepared_case(tmp_path, monkeypatch) as c:
        c.preparation.authority.denied = True
        with pytest.raises(PermissionError):
            c.authority.authorize_start(c.browser.spec, c.browser.op, guard())
        assert not c.browser.channels


def test_lost_preparation_does_not_block_original_browser_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with prepared_case(tmp_path, monkeypatch) as c:
        b = c.browser
        with registered_browser(
            b.spec,
            b.op,
            journal=b.journal,
            evidence=b.evidence,
            controls=b.controls,
            clock=b.clock,
            authority=c.authority,
        ):
            c.preparation.authority.denied = True
            ref = c.binding.publication.prepared_ref
            (tmp_path / "site/evidence/blobs" / ref.sha256).unlink()
        assert b.journal.read(b.spec.token, b.op).state == "closed"


def test_closed_site_cannot_authorize_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with prepared_case(tmp_path, monkeypatch) as c:
        pass
    with pytest.raises(OwnershipConflict, match="acquired site"):
        c.binding.verify(c.browser.spec, c.browser.op, guard())


def test_cancellation_before_dependency_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with prepared_case(tmp_path, monkeypatch) as c:

        class Cancel:
            def checkpoint(self) -> float:
                raise PermissionError("cancelled")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        with pytest.raises(PermissionError, match="cancelled"):
            c.binding.verify(c.browser.spec, c.browser.op, Cancel())
        assert not c.browser.channels


def test_replaced_initial_observation_rejected_and_original_browser_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with prepared_case(tmp_path, monkeypatch) as c:
        b = c.browser
        original = c.authority.verify_started

        def replace(
            spec: BrowserResourceSpec,
            started: BrowserResourceStarted,
            operation: OperationContext,
            control: OperationControl,
        ) -> None:
            observed = Observation.model_validate_json(
                b.evidence.read(started.initial_observation_ref, control=control)
            )
            changed = put(
                b.evidence,
                observed.model_copy(update={"text": "other observation"}),
                "public",
            )
            original(
                spec,
                started.model_copy(update={"initial_observation_ref": changed}),
                operation,
                control,
            )

        monkeypatch.setattr(c.authority, "verify_started", replace)
        with pytest.raises(OwnershipConflict, match="Initial browser return"):
            with registered_browser(
                b.spec,
                b.op,
                journal=b.journal,
                evidence=b.evidence,
                controls=b.controls,
                clock=b.clock,
                authority=c.authority,
            ):
                pytest.fail("Cannot yield a substituted observation")
        assert b.journal.read(b.spec.token, b.op).state == "closed"
        assert b.channels[0].engine.calls == ["start", "close"]


@pytest.mark.parametrize("phase", ["start", "started"])
def test_external_resource_authority_is_still_mandatory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    with prepared_case(tmp_path, monkeypatch) as c:
        b = c.browser
        if phase == "start":
            b.authority.deny_start = True
        else:
            b.authority.deny_started = True
        with pytest.raises(PermissionError):
            with registered_browser(
                b.spec,
                b.op,
                journal=b.journal,
                evidence=b.evidence,
                controls=b.controls,
                clock=b.clock,
                authority=c.authority,
            ):
                pytest.fail("Bound preparation cannot override resource denial")
        if phase == "start":
            assert not b.channels
        else:
            assert b.journal.read(b.spec.token, b.op).state == "closed"
