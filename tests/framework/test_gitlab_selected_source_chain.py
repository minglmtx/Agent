"""Actual source orchestration on isolated synthetic native/browser ports."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.sites.gitlab.tasks.group_recovery import GroupObserved
from lab_generate_skill.adapters.plans.reset_evidence import ResetEvidenceReader
from gitlab_source_assembly_fixture import selected_group_source
from gitlab_group_evaluator_fixtures import evaluation_case
from gitlab_group_preparation_fixtures import put as put_group
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)
from gitlab_actor_review import review_gitlab_judgment, review_gitlab_reset
from gitlab_group_review_process import closed_group_review
from site_capture_native import capture_original
from source_task_evaluation import judge_source_task
from source_review_records import ReadOnlyEvidence
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "fault", ["none", "wrong-snapshot", "missing-closure", "bad-resume-result"]
)
def test_actual_group_source_chooses_group_preparation_unique_initial_capture_and_safe_reset(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with selected_group_source(tmp_path, node_path, monkeypatch) as c:
        source, n, live = c.source, c.source.native, c.source.site
        assert n.public.identity.family == "group_creation"
        original = c.request("snapshot")
        result = live.tasks.execute_task(original, control=guard())
        ref = n.raw(result.private_result.encode(), "gitlab-group-recovery/1")
        if fault == "wrong-snapshot":
            with pytest.raises(AssertionError):
                source.after_snapshot(
                    original.model_copy(update={"binding_ref": n.spec_ref}), result, ref
                )
            assert "environment_ref" not in source.saved
            return
        source.after_snapshot(original, result, ref)
        request = c.request("prepare", ref)
        prepared = live.tasks.execute_task(request, control=guard())
        publication = n.publish(
            request, prepared, live.site.instance, environment=source.environment
        )
        before = capture_original(c.site, live, request, "before")
        observed = source.observe(
            PreparedPublication.model_validate(publication["publication"]),
            tmp_path / "browser",
            monkeypatch,
        )
        assert (
            observed["complete_baseline"] and source.saved["baseline"].status == "ready"
        )
        b = c.browsers[0]
        assert isinstance(
            b.spec.configuration.initialization, GitlabGroupInitialization
        )
        assert b.channels[0].engine.calls == ["start", "close"]
        assert (
            source.saved["baseline"].observation_ref
            == source.saved["baseline_inputs"].observation_ref
        )
        after = capture_original(c.site, live, request, "after")
        first = GroupObserved.model_validate_json(json.dumps(before["catalog"]))
        last = GroupObserved.model_validate_json(json.dumps(after["catalog"]))
        assert c.site.evidence.read(
            first.native.payload_ref, guard()
        ) == c.site.evidence.read(last.native.payload_ref, guard())
        calls = len(c.native.sql.calls)
        blobs = tuple(sorted((tmp_path / "evidence/blobs").iterdir()))
        assert len(c.native.task.instance.generations) == 2
        if fault == "missing-closure":
            source.saved["browser_closed_before_restore"] = False
            absent: Any = None
            with pytest.raises(AssertionError):
                source.after_restore(c.request("restore", ref), absent)
            assert (
                len(c.native.sql.calls) == calls
                and len(c.native.task.instance.generations) == 2
            )
            assert tuple(sorted((tmp_path / "evidence/blobs").iterdir())) == blobs
            return
        restore = c.request("restore", ref)
        restored = live.tasks.execute_task(restore, control=guard())
        if fault == "bad-resume-result":
            from gitlab_resume_native import resume_original

            calls = len(c.native.sql.calls)
            blobs = tuple(sorted((tmp_path / "evidence/blobs").iterdir()))
            with pytest.raises(
                ValueError, match="original restore request/result/site"
            ):
                resume_original(
                    c.site,
                    live,
                    restore,
                    restored.model_copy(update={"request_sha256": "f" * 64}),
                    source.saved["browser_closure_ref"],
                )
            assert (
                len(c.native.sql.calls) == calls
                and len(c.native.task.instance.generations) == 3
            )
            assert tuple(sorted((tmp_path / "evidence/blobs").iterdir())) == blobs
        reset = source.after_restore(restore, restored)
        assert (
            reset["reset_status"] == "safe"
            and len(c.native.task.instance.generations) == 3
        )
        readonly = ReadOnlyEvidence(tmp_path / "evidence")
        inputs = ResetEvidenceReader(readonly).verify(source.saved["reset"], guard())
        calls = len(c.native.sql.calls)
        review_gitlab_reset({"qualified_source": reset}, inputs, readonly, guard())
        review_gitlab_reset({"qualified_source": reset}, inputs, readonly, guard())
        assert len(c.native.sql.calls) == calls


@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("projects", [False, True])
def test_actual_group_judgment_bridge_and_whole_reviewer_choose_concrete_group(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    saved: bool,
    projects: bool,
) -> None:
    with evaluation_case(
        tmp_path, node_path, monkeypatch, saved=saved, projects_changed=projects
    ) as c:
        p = c.source.preparation
        source: Any = SimpleNamespace(
            native=SimpleNamespace(
                public=p.inputs.public_task,
                binding=p.inputs.binding,
                binding_ref=c.contract.task_contract_ref,
                put=lambda value: put_group(p.store, value),
            ),
            c=SimpleNamespace(
                evidence=p.store, spec=SimpleNamespace(configuration=p.configuration)
            ),
            saved={
                "environment_selection_ref": c.selected.environment_ref,
                "browser_spec_ref": c.selected.browser_spec_ref,
                "baseline_inputs": SimpleNamespace(
                    prepared=SimpleNamespace(scope=c.trace.scope)
                ),
            },
        )
        assert (
            c.selected.before
            and c.selected.after
            and c.selected.page
            and c.selected.trace_ref
        )
        facts = {
            "catalog_before": c.selected.before.model_dump(mode="json"),
            "catalog_after": c.selected.after.model_dump(mode="json"),
        }
        actor = {
            "page_capture": c.selected.page.model_dump(mode="json"),
            "trace_ref": c.selected.trace_ref.model_dump(mode="json"),
        }
        calls = len(p.native.sql.calls)
        result = judge_source_task(source, facts, actor)
        evaluation = Evaluation.model_validate_json(json.dumps(result["evaluation"]))
        expected = (
            "unknown" if saved and projects else "success" if saved else "failure"
        )
        assert evaluation.status == expected
        readonly = ReadOnlyEvidence(node_path / "private-evidence")
        reviewed = review_gitlab_judgment(
            c.contract, c.selected, evaluation, readonly, guard()
        )
        assert reviewed == closed_group_review(
            tmp_path, node_path / "private-evidence", c.contract, c.selected, evaluation
        )
        assert reviewed["business_accepted"] == (expected != "unknown")
        assert len(p.native.sql.calls) == calls
