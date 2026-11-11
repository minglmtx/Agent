"""Typed construction identities through original selected8 source combination.

All native/model/rights are declared doubles. These tests do not admit a source,
claim a pending live construction or authorize a fresh original request.
"""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.construction import AttemptIntent
from lab_generate_skill.domain.execution import AttemptBinding, RunBinding
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.sites.map.tasks.navigation_recovery import NavigationSnapshot
from map_navigation_group_cases import SOURCES
from map_navigation_source_fixtures import selection, source_combination
from map_navigation_evaluation_fixtures import closed_review
from map_registered_worker_fixtures import RegisteredMapCase
from map_source_inputs import source_inputs, engineering_scope
from site_worker_fixtures import configuration
from test_core_contracts import reference
from test_map_source_inputs import source_case as source_case, SourceCase
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def original_intent_scope(source: str) -> tuple[AttemptIntent, StateScope]:
    selected = selection(source)
    owner = configuration(job_id="4752096").token.owner
    intent = AttemptIntent(
        binding=AttemptBinding(
            run=RunBinding(
                owner=owner,
                plan_ref=reference("private", "run-plan/1"),
                release_ref=reference("private", "release-manifest/1"),
                submission_key="original-construction",
            ),
            attempt_id="candidate-0-first-" + source,
            task=selected.public_template.identity,
            claim_ref=reference("private", "source-claim/1"),
        ),
        candidate_slot=0,
        skill_digest="0" * 64,
        public_context_ref=reference("public", "public-construction-context/1"),
    )
    return intent, StateScope(
        owner=intent.binding.run.owner,
        task=intent.binding.task,
        attempt_id=intent.binding.attempt_id,
        context_id="qualified-context-" + source,
    )


@pytest.mark.parametrize("source", SOURCES)
def test_all8_constructed_attempt_scope_through_fixed_source_review_and_reset(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    intent, scope = original_intent_scope(source)
    c = RegisteredMapCase(
        node_path, monkeypatch, navigation_source=source, task_scope=scope
    )
    try:
        assert c.configuration.map_inputs is not None
        assert c.configuration.map_inputs.scope == scope
        facts = source_combination(c, monkeypatch)
        closed_review(c, facts)
        assert (
            facts["judgment"]["evaluation"]["attempt_id"] == intent.binding.attempt_id
        )
        snapshot = NavigationSnapshot.model_validate_json(
            c.resource.evidence.read(
                EvidenceRef.model_validate(facts["snapshot"]["snapshot_ref"]),
                control=guard(),
            )
        )
        assert snapshot.native.plan.scope == scope
        request = SiteTaskRequest.model_validate_json(
            c.resource.evidence.read(
                EvidenceRef.model_validate(facts["snapshot"]["request"]),
                control=guard(),
            )
        )
        assert request.operation.attempt_id == intent.binding.attempt_id
        assert facts["qualified_source"]["reset_status"] == "safe"
    finally:
        c.close_sockets()


@pytest.mark.parametrize("fault", ["empty", "wrong-type", "owner", "task", "heldout"])
def test_bad_source_scope_is_rejected_before_metadata_or_CAS(
    source_case: SourceCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    root, evidence, parent, base, store = source_case
    chosen = selection(SOURCES[0])
    scope: Any = engineering_scope(base.token.owner, chosen)
    if fault == "empty":
        scope = None
    elif fault == "wrong-type":
        scope = {}
    elif fault == "owner":
        scope = scope.model_copy(
            update={"owner": scope.owner.model_copy(update={"owner_id": "foreign"})}
        )
    else:
        task = (
            selection(SOURCES[1]).public_template.identity
            if fault == "task"
            else scope.task.model_copy(update={"split": "test"})
        )
        scope = scope.model_copy(update={"task": task})

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail(
            "Invalid original scope must reject before reading metadata or publishing CAS"
        )

    monkeypatch.setattr("map_source_inputs.read_pinned_bytes", forbidden)
    monkeypatch.setattr(store, "put", forbidden)
    with pytest.raises((TypeError, ValueError)):
        source_inputs(
            store,
            base.token.owner,
            base.installation,
            root,
            parent,
            guard(),
            scope=scope,
            evidence_root=evidence,
            selection=chosen,
        )
    assert not list(parent.iterdir())


@pytest.mark.parametrize("outcome", ["valid-negative", "unknown"])
def test_constructed_scope_error_keeps_original_identity_and_safe_reset(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    source = SOURCES[0]
    intent, scope = original_intent_scope(source)
    c = RegisteredMapCase(
        node_path, monkeypatch, navigation_source=source, task_scope=scope
    )
    try:
        facts = source_combination(
            c,
            monkeypatch,
            negative=outcome == "valid-negative",
            missing_trace=outcome == "unknown",
        )
        if outcome == "valid-negative":
            closed_review(c, facts)
        result = facts["judgment"]["evaluation"]
        assert result["attempt_id"] == intent.binding.attempt_id
        assert result["status"] == (
            "failure" if outcome == "valid-negative" else "unknown"
        )
        assert facts["qualified_source"]["reset_status"] == "safe"
    finally:
        c.close_sockets()
