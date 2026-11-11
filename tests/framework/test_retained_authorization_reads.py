"""Retained parent proof with fresh gates; original data, isolated effects only."""

from collections import Counter
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from lab_generate_skill.adapters.plans.stage_parent import RetainedStageParentChecks
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from construction_storage_fixtures import put
from stage_admission_fixtures import retained_case, operation_controls, stage_plan


class CurrentChecks:
    def __init__(self):
        self.calls = 0
        self.deny_at = None

    def check_current(self, control):
        control.checkpoint()
        self.calls += 1
        if self.deny_at is not None and self.calls >= self.deny_at:
            raise PermissionError("current storage revoked")


def case(tmp_path, monkeypatch, site="map", selected=True):
    c = retained_case(tmp_path, site)
    op, controls, owner = operation_controls()
    target = put(c.store, {"isolated_parent_read_delta": True}, "release-manifest/1")
    run, binding = stage_plan(c, owner, target)
    original = c.checker(binding, target, controls)
    current = CurrentChecks()
    parent = RetainedStageParentChecks(
        original.origin,
        binding,
        original.authorization_id,
        c.store,
        controls,
        current_checks=current if selected else None,
    )
    counts = Counter()
    read = c.store.read

    def counted(ref, control=None):
        counts[ref] += 1
        return read(ref, control)

    monkeypatch.setattr(c.store, "read", counted)
    return c, op, controls, run, binding, parent, current, counts


@pytest.mark.parametrize("site", ["admin", "map"])
def test_repeated_parent_consumption_reads_authorization_once(
    tmp_path, monkeypatch, site
):
    c, op, controls, run, binding, parent, current, counts = case(
        tmp_path, monkeypatch, site
    )
    facts = parent.data(op)
    first = counts.copy()
    for _ in range(3):
        assert parent.data(op) is facts
    assert counts == first
    assert counts[parent.origin.validation.authorization_ref] == 1
    assert current.calls == 8
    assert facts.source == c.source
    # Both the before and after gate remain effective on retained consumption.
    current.deny_at = current.calls + 2
    with pytest.raises(PermissionError):
        parent.data(op)
    with pytest.raises(PermissionError):
        parent.data(op)
    assert counts == first


@pytest.mark.parametrize("fault", ["selection", "origin", "expired"])
def test_retained_data_never_accepts_changed_scope_or_expiration(
    tmp_path, monkeypatch, fault
):
    c, op, controls, run, binding, parent, current, counts = case(tmp_path, monkeypatch)
    parent.data(op)
    if fault == "selection":
        parent.authorization_id = "different-selection"
    elif fault == "origin":
        ref = parent.origin.validation.authorization_ref.model_copy(
            update={"producer": "changed"}
        )
        validation = parent.origin.validation.model_copy(
            update={"authorization_ref": ref}
        )
        parent.origin = parent.origin.model_copy(update={"validation": validation})
    else:
        op = op.model_copy(update={"deadline": op.deadline - timedelta(days=1)})
    with pytest.raises((OwnershipConflict, OperationStopped)):
        parent.data(op)


def test_legacy_reader_keeps_controlled_reads(tmp_path, monkeypatch):
    c, op, controls, run, binding, parent, current, counts = case(
        tmp_path, monkeypatch, selected=False
    )
    parent.data(op)
    parent.data(op)
    assert counts[parent.origin.validation.authorization_ref] == 2
    assert current.calls == 0


def test_actual_bootstrap_binds_same_store_current_checks_before_effects(
    tmp_path, monkeypatch
):
    import lab_generate_skill.bootstrap.stage_execution_admission as entry

    c, op, controls, run, binding, parent, current, counts = case(tmp_path, monkeypatch)
    transport = SimpleNamespace(store=c.store)
    root = c.shadow_claim_root(tmp_path / "claims")
    constructed = []

    class StopBeforeEffects(Exception):
        pass

    def constructor(*args, **kwargs):
        value = RetainedStageParentChecks(*args, **kwargs)
        assert value.current_checks is transport
        constructed.append(value)
        raise StopBeforeEffects

    monkeypatch.setattr(entry, "RetainedStageParentChecks", constructor)
    args = (run, binding.run, parent.origin, None, transport, None, None, op)
    kwargs = dict(
        authorization_id=parent.authorization_id,
        claim_root=root,
        claim_scope=binding.scope_id,
        evidence=c.store,
        controls=controls,
        expected_site=binding.task.identity.site,
    )
    with pytest.raises(StopBeforeEffects):
        entry.admit_stage_validation_source(*args, **kwargs)
    assert len(constructed) == 1
    transport.store = object()
    with pytest.raises(OwnershipConflict, match="same store"):
        entry.admit_stage_validation_source(*args, **kwargs)
    assert len(constructed) == 1
