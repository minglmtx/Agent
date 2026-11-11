"""Initial checks preserve a single original observation and never grant Actor rights."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.initial_observation import (
    InitialObservationSelection,
    InitialObservationInputs,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceNotFound,
    EvidenceIntegrityError,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.state_scope import StateCommitUnconfirmed
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from initial_observation_fixtures import initial_case
from preparation_record_fixtures import put
from test_slurm_commands import guard


def test_publish_and_reconcile_only_initial_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        before = set((tmp_path / "site/evidence/blobs").iterdir())
        ref = c.records.publish(c.selection, c.op)
        value = c.records.load(c.selection, ref, c.op)
        assert value.checks.status == "pass"
        assert set((tmp_path / "site/evidence/blobs").iterdir()) - before == {
            tmp_path / "site/evidence/blobs" / ref.sha256
        }
        returned = c.prepared.browser.channels[0].engine.last_readout
        assert returned is not None
        assert (
            value.observation_ref
            == c.records.reader.load(
                c.selection, c.op, guard()
            ).acquired.details.started.initial_observation_ref
        )
        cleanup = c.op.cleanup(
            "initial-checks-reconcile", now=datetime.now(timezone.utc), seconds=20
        )
        assert c.records.load(c.selection, ref, cleanup) == value
        assert value.operation == c.op and c.authority.calls == 3
        assert c.prepared.preparation.environment.checks.status == "unknown"
        assert c.prepared.browser.channels[0].engine.calls == ["start"]


@pytest.mark.parametrize("fault", ["foreign_worker_reference", "old_resource"])
def test_original_worker_binding_cannot_be_replaced_in_initial_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    from pydantic import ValidationError

    with initial_case(tmp_path, monkeypatch) as c:
        inputs = c.records.reader.load(c.selection, c.op, guard())
        value = inputs.model_dump()
        if fault == "foreign_worker_reference":
            value["acquired"]["details"]["worker_acquired_ref"].update(
                sha256="f" * 64, uri="cas://sha256/" + "f" * 64
            )
            with pytest.raises(
                OwnershipConflict, match="exact original worker reference"
            ):
                InitialObservationInputs.model_validate(value)
        else:
            value["browser"]["schema_version"] = "browser-resource-spec/3"
            with pytest.raises(ValidationError):
                InitialObservationInputs.model_validate(value)


@pytest.mark.parametrize("field", ["browser_spec_ref", "browser_acquired_ref"])
@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_dependency_fault_preserved_without_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, fault: str
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        ref = getattr(c.selection, field)
        path = tmp_path / "site/evidence/blobs" / ref.sha256
        if fault == "missing":
            path.unlink()
        else:
            path.write_bytes(b"corrupt")
        before = set(path.parent.iterdir())
        with pytest.raises(
            EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
        ):
            c.records.publish(c.selection, c.op)
        assert set(path.parent.iterdir()) == before and c.authority.calls == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "old/1"),
        ("browser_spec_ref", None),
        ("preparation", {}),
        ("browser_acquired_ref", "text"),
    ],
)
def test_invalid_selection_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        with pytest.raises(ValueError):
            InitialObservationSelection.model_validate(
                {**c.selection.model_dump(), field: value}
            )


@pytest.mark.parametrize(
    "field,value",
    [("owner_id", "other"), ("attempt_id", "other"), ("operation_id", "acquire")],
)
def test_check_operation_must_be_distinct_and_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        before = c.prepared.preparation.authority.calls
        with pytest.raises((OwnershipConflict, ValueError)):
            c.records.publish(c.selection, c.op.model_copy(update={field: value}))
        assert c.authority.calls == 0
        if field in ("owner_id", "attempt_id"):
            assert c.prepared.preparation.authority.calls == before


def test_denied_load_and_forged_summary_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        ref = c.records.publish(c.selection, c.op)
        value = c.records.load(c.selection, ref, c.op)
        changed = put(
            c.prepared.browser.evidence,
            value.model_copy(update={"measured_state_sha256": "0" * 64}),
        )
        with pytest.raises(OwnershipConflict, match="differ"):
            c.records.load(c.selection, changed, c.op)
        c.authority.denied = True
        with pytest.raises(PermissionError):
            c.records.load(c.selection, ref, c.op)
        with pytest.raises(PermissionError):
            c.records.publish(c.selection, c.op)


@pytest.mark.parametrize("change", ["loading", "wrong_url", "empty", "terminal"])
def test_unready_view_does_not_pass_site_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        inputs = c.records.reader.load(c.selection, c.op, guard())
        observed = inputs.observation.record
        if change == "loading":
            observed = observed.model_copy(update={"state": "loading"})
        elif change == "wrong_url":
            observed = observed.model_copy(
                update={
                    "tabs": (
                        observed.tabs[0].model_copy(
                            update={"url": "http://127.0.0.1:12001/admin"}
                        ),
                    )
                }
            )
        elif change == "empty":
            observed = observed.model_copy(update={"text": ""})
        returned = inputs.returned.model_copy(
            update={"observation": observed, "terminated": change == "terminal"}
        )
        inputs = inputs.model_copy(
            update={
                "returned": returned,
                "observation": inputs.observation.model_copy(
                    update={"record": observed, "text": observed.text}
                ),
            }
        )
        assert c.records.checks.check(inputs, guard()).status == "fail"


def test_put_returns_wrong_reference_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        original = c.records.store.put

        def wrong(
            data: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            return original(data, metadata, control=control).model_copy(
                update={"producer": "other"}
            )

        with monkeypatch.context() as patch:
            patch.setattr(c.records.store, "put", wrong)
            with pytest.raises(EvidenceIntegrityError) as error:
                c.records.publish(c.selection, c.op)
        assert error.value.candidate_reference.content_schema == "initial-state-checks/1"  # type: ignore[attr-defined]


def test_narrowed_site_check_coverage_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:

        class WrongChecks:
            def check(
                self, inputs: InitialObservationInputs, control: OperationControl
            ) -> StateChecks:
                return StateChecks(required=("other",))

        c.records.checks = WrongChecks()
        with pytest.raises(OwnershipConflict, match="coverage"):
            c.records.publish(c.selection, c.op)
        assert c.authority.calls == 0


def test_post_commit_failure_keeps_original_reference_for_read_only_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        delegate = c.records.controls.bind(c.op)
        stopped = False

        class Control:
            def checkpoint(self) -> float:
                if stopped:
                    raise RuntimeError("acknowledgement lost")
                return delegate.checkpoint()

            def wait(self, seconds: float) -> None:
                delegate.wait(seconds)

        original = c.records.store.put

        def committed(
            data: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            nonlocal stopped
            reference = original(data, metadata, control=control)
            stopped = True
            return reference

        with monkeypatch.context() as patch:
            patch.setattr(c.records.controls, "bind", lambda op: Control())
            patch.setattr(c.records.store, "put", committed)
            with pytest.raises(StateCommitUnconfirmed) as error:
                c.records.publish(c.selection, c.op)
        stopped = False
        cleanup = c.op.cleanup(
            "read-original-checks", now=datetime.now(timezone.utc), seconds=20
        )
        value = c.records.load(c.selection, error.value.reference, cleanup)
        assert value.operation == c.op and value.checks.status == "pass"
        assert c.prepared.browser.channels[0].engine.calls == ["start"]


@pytest.mark.parametrize("committed", [False, True])
def test_unconfirmed_put_keeps_candidate_without_claiming_existence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, committed: bool
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        original = c.records.store.put
        failure = OSError("put acknowledgement unknown")

        def unknown(
            data: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            if committed:
                original(data, metadata, control=control)
            raise failure

        with monkeypatch.context() as patch:
            patch.setattr(c.records.store, "put", unknown)
            with pytest.raises(OSError) as error:
                c.records.publish(c.selection, c.op)
        assert error.value is failure
        candidate = getattr(error.value, "initial_checks_candidate_reference")
        cleanup = c.op.cleanup(
            "inspect-uncertain-checks", now=datetime.now(timezone.utc), seconds=20
        )
        if committed:
            assert (
                c.records.load(c.selection, candidate, cleanup).checks.status == "pass"
            )
        else:
            with pytest.raises(EvidenceNotFound):
                c.records.load(c.selection, candidate, cleanup)
        assert c.prepared.browser.channels[0].engine.calls == ["start"]
