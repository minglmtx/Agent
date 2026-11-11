"""Original conditional-goal review on real CAS, with synthetic site/Actor effects."""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.reddit_image_evaluation import reddit_image_evaluator
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from reddit_evaluator_fixtures import evaluation_case
from reddit_actor_review import review_reddit_judgment
from source_review_records import ReadOnlyEvidence
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "case", ["success", "failure", "missing", "different", "cancel", "title-not-issued"]
)
def test_independent_native_oracle_readonly_repeat_unknown_and_rejection(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    with evaluation_case(
        tmp_path,
        node_path,
        monkeypatch,
        saved=case != "failure",
        issued_title=case != "title-not-issued",
    ) as c:
        selected = (
            c.selected.model_copy(update={"after": None})
            if case == "missing"
            else c.selected
        )
        store = ReadOnlyEvidence(node_path / "private-evidence")
        saved = reddit_image_evaluator(selected).evaluate(c.contract, store, guard())
        before = tuple(sorted((node_path / "private-evidence/blobs").iterdir()))
        calls = c.source.preparation.native.reader.calls
        if case == "different":
            with pytest.raises(EvidenceIntegrityError, match="evaluation differs"):
                review_reddit_judgment(
                    c.contract,
                    selected,
                    saved.model_copy(update={"reason_code": "FOREIGN"}),
                    store,
                    guard(),
                )
        elif case == "cancel":
            with pytest.raises(OperationStopped):
                review_reddit_judgment(c.contract, selected, saved, store, guard(0))
        else:
            first = review_reddit_judgment(c.contract, selected, saved, store, guard())
            assert first == review_reddit_judgment(
                c.contract, selected, saved, store, guard()
            )
            assert first["original_oracle"] == (
                "not_run" if case == "missing" else "conditional_checks_equal"
            )
            assert first["business_accepted"] == (case != "missing")
            if case != "missing":
                assert len(first["checked_names"]) == (2 if case == "failure" else 8)
        assert c.source.preparation.native.reader.calls == calls
        assert tuple(sorted((node_path / "private-evidence/blobs").iterdir())) == before


@pytest.mark.parametrize(
    "fault", ["none", "different", "missing_closure", "changed_resumed_native"]
)
def test_original_full_restore_and_resume_review_is_readonly(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from datetime import datetime, timezone
    from lab_generate_skill.domain.lifecycle import ClosureReceipt
    from lab_generate_skill.domain.site_resume import SiteResumeResult
    from lab_generate_skill.sites.reddit.tasks.image_recovery import ImageResumed
    from lab_generate_skill.bootstrap.reddit_image_records import (
        reddit_state_qualifications,
    )
    from lab_generate_skill.adapters.clock import SystemClock
    from lab_generate_skill.runtime.lifecycle import OperationGuards
    from reddit_qualification_fixtures import restore
    from reddit_preparation_fixtures import put
    from reddit_actor_review import review_reddit_reset
    from test_resource_journal import NoCancellation
    from lab_generate_skill.domain.errors import OwnershipConflict

    with evaluation_case(tmp_path, node_path, monkeypatch, saved=False) as c:
        p = c.source.preparation
        closure = ClosureReceipt(
            token=c.browser.token,
            operation_id="explicit-synthetic-browser-close",
            status="closed",
            evidence=(c.source.environment.spec_ref,),
        )
        closure_ref = put(p.store, closure)
        selection = restore(c.source, (c.browser.token,), (closure_ref,))
        ref = put(p.store, selection)
        controls = OperationGuards(SystemClock(), NoCancellation())
        records = reddit_state_qualifications(p.store, controls, c.source.authority)
        op = p.inputs.request.operation.cleanup(
            "unit-review-reset", now=datetime.now(timezone.utc), seconds=30
        ).model_copy(update={"recovery_ref": c.source.site.token.recovery_ref})
        inputs = records.publish_reset_facts(ref, op)
        if fault == "different":
            inputs = inputs.model_copy(
                update={
                    "plan": inputs.plan.model_copy(
                        update={"parent_operation_id": "foreign"}
                    )
                }
            )
        elif fault == "missing_closure":
            selection = selection.model_copy(
                update={
                    "closure_refs": (
                        put(
                            p.store,
                            closure.model_copy(update={"status": "unconfirmed"}),
                        ),
                    )
                }
            )
            ref = put(p.store, selection)
        elif fault == "changed_resumed_native":
            result = SiteResumeResult.model_validate_json(
                p.store.read(selection.resume_result_ref)
            )
            resumed = ImageResumed.model_validate_json(result.private_result)
            (
                node_path / "private-evidence/blobs" / resumed.native.payload_ref.sha256
            ).write_bytes(b"{}")
        site = {
            "qualified_source": {"reset_selection_ref": ref.model_dump(mode="json")}
        }
        store = ReadOnlyEvidence(node_path / "private-evidence")
        calls = p.native.reader.calls
        blobs = tuple(sorted((node_path / "private-evidence/blobs").iterdir()))
        if fault == "none":
            for _ in range(2):
                review_reddit_reset(site, inputs, store, guard())
        else:
            with pytest.raises((EvidenceIntegrityError, OwnershipConflict, ValueError)):
                review_reddit_reset(site, inputs, store, guard())
        assert p.native.reader.calls == calls
        assert tuple(sorted((node_path / "private-evidence/blobs").iterdir())) == blobs
