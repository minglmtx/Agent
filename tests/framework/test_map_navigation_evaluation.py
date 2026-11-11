"""Current unified Evaluator and independent Reset on the full selected8 group."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.evaluators.map.navigation import CHECKS
from map_navigation_terminal_fixtures import terminal_navigation
from map_navigation_evaluation_fixtures import (
    retain_closed_proof,
    facts,
    contract,
    evaluator,
    selected,
    closed_review,
    bind_original_contract,
)
from map_navigation_browser_fixtures import CancelledControl
from map_navigation_group_cases import SOURCES
from map_registered_worker_fixtures import RegisteredMapCase
from preparation_record_fixtures import put
from test_site_resource import inspect
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize("source", SOURCES)
def test_each_member_unified_original_judgment_then_fresh_closed_readonly_reset(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source)
    bind_original_contract(c)
    retain_closed_proof(monkeypatch)
    try:
        with terminal_navigation(c, monkeypatch) as t:
            e = evaluator(t)
            # Exercise the real graph before errors are deliberately classified unknown.
            outcome = e.loader(contract(t), selected(t), c.resource.evidence, guard(60))
            assert outcome.status == "success"
            saved = e.evaluate(contract(t), c.resource.evidence, guard(60))
            assert saved.status == "success" and saved.reward == 1
            assert tuple(x.name for x in saved.checks) == CHECKS
            assert all(x.status == "pass" for x in saved.checks)
            result = facts(t)
        closed_review(c, result)
        assert c.worker is not None and c.worker.references is None
    finally:
        c.close_sockets()


def test_original_failure_missing_partial_and_cancelled_evidence_never_resend(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    bind_original_contract(c)
    retain_closed_proof(monkeypatch)
    try:
        with terminal_navigation(c, monkeypatch, negative=True) as t:
            store = c.resource.evidence
            before = (
                list(t.initial.calls),
                list(t.initial.page.calls),
                len(c.sql.calls),
            )
            e, declared, good = evaluator(t), contract(t), selected(t)
            assert e.evaluate(declared, store, guard(60)).status == "failure"
            assert e.evaluate(declared, store, guard(60)).reward == 0
            for field in (
                "environment_ref",
                "terminal_ref",
                "final_guard",
                "browser_closure_ref",
            ):
                result = evaluator(t, good.model_copy(update={field: None})).evaluate(
                    declared, store, guard(60)
                )
                assert result.status == "unknown" and result.reward is None
            bad = ClosureReceipt.model_validate_json(
                store.read(t.closure_ref)
            ).model_copy(update={"operation_id": "foreign-close"})
            result = evaluator(
                t, good.model_copy(update={"browser_closure_ref": put(store, bad)})
            ).evaluate(declared, store, guard(60))
            assert result.status == "unknown" and result.reward is None
            with pytest.raises(OperationStopped):
                e.evaluate(declared, store, CancelledControl())
            assert (t.initial.calls, t.initial.page.calls, len(c.sql.calls)) == before
            retained = facts(t)
        closed_review(c, retained)
    finally:
        c.close_sockets()
