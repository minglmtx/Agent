"""Actual owned lifecycle consumes bodies and skips only invariant checks."""

import copy
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.plans.trace_journal_evidence import (
    TraceJournalEvidence,
)
from lab_generate_skill.bootstrap.owned_preparation_records import (
    owned_preparation_records,
)
from lab_generate_skill.domain.trace_events import InteractionObserved
from lab_generate_skill.ports.preparation_records import PreparationInputReads
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import OwnershipConflict
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("changed_checker", [False, True])
def test_owned_browser_reuses_exact_inputs_but_checker_change_only_rechecks_that_component(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, changed_checker: bool
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed = fixed_task_source_inputs(c, r, monkeypatch)
        assert r.inputs is not None
        assert isinstance(c.journals.source_reader.contexts, PreparationInputReads)
        c.bundle.preparation.records = owned_preparation_records(
            c.bundle.preparation.records,
            c.journals.source_reader.contexts,
            inputs=r.inputs,
        )
        original = PreparedBrowserBinding.verify
        calls = semantic_checks = 0
        static_reads: list[str] = []

        def verify(binding: Any, *args: Any) -> Any:
            nonlocal calls, semantic_checks
            calls += 1
            if calls == 1:
                check = binding.task_checks.check
                parse = binding.reads.parse

                def counted(*a: Any, **kw: Any) -> Any:
                    nonlocal semantic_checks
                    semantic_checks += 1
                    return check(*a, **kw)

                def read(ref: Any, schema: str, *a: Any, **kw: Any) -> Any:
                    static_reads.append(schema)
                    return parse(ref, schema, *a, **kw)

                monkeypatch.setattr(binding.task_checks, "check", counted)
                monkeypatch.setattr(binding.reads, "parse", read)
            if calls == 3 and changed_checker:
                binding.task_checks = copy.copy(binding.task_checks)
            return original(binding, *args)

        monkeypatch.setattr(PreparedBrowserBinding, "verify", verify)
        result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert result.evaluation.status == "success" and calls >= 4
        assert semantic_checks == (2 if changed_checker else 1)
        assert static_reads.count("site-resource-started/1") == 1
        assert static_reads.count("site-task-request/2") == 1
        assert static_reads.count("environment-baseline/1") == 1
        assert fixed.current_calls > calls
        assert not r.inputs.active and r.inputs.prepared_browser is None


@pytest.mark.parametrize("fault", ["none", "revoked", "missing_return"])
def test_trace_registration_consumes_actual_publisher_bytes_without_reading_return_again(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed = fixed_task_source_inputs(c, r, monkeypatch)
        original = TraceJournalEvidence.event
        committed = 0
        attempts = 0

        def event(
            verifier: Any,
            before: Any,
            after: Any,
            item: Any,
            op: Any,
            control: Any,
            **kwargs: Any,
        ) -> Any:
            nonlocal committed, attempts
            if (
                not isinstance(item, InteractionObserved)
                or item.interaction.result is None
            ):
                return original(verifier, before, after, item, op, control, **kwargs)
            browser = r.browser()
            assert browser is not None
            published = browser.session.published_step
            assert published is not None and published.result == item.interaction.result
            attempts += 1
            if fault == "revoked":
                fixed.denied = True
            elif fault == "missing_return":
                browser.session.published_step = None
            reader = published.remaining
            physical = reader.read
            refs = {body.reference for body in published.bodies}
            repeated: list[Any] = []

            def read(ref: Any, *args: Any, **kw: Any) -> bytes:
                if ref in refs:
                    repeated.append(ref)
                return physical(ref, *args, **kw)

            with monkeypatch.context() as patch:
                patch.setattr(reader, "read", read)
                value = original(verifier, before, after, item, op, control, **kwargs)
            assert repeated == []
            committed += 1
            return value

        monkeypatch.setattr(TraceJournalEvidence, "event", event)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success" and result.interactions == 1
            assert committed == 1
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as failed:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            error = failed.value.primary
            chain: list[BaseException] = []
            while error is not None and len(chain) < 16:
                chain.append(error)
                error = getattr(error, "primary", None) or error.__cause__
            assert any(isinstance(error, OwnershipConflict) for error in chain), chain
            assert committed == 0
        assert attempts == 1
