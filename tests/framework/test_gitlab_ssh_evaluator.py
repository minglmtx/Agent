"""Complete original evidence joins; fake effects never assert real Actor/site support."""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_ssh_evaluation import gitlab_ssh_evaluator
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.evidence import EvidenceRequirements
from lab_generate_skill.sites.gitlab.evidence_schema import GitlabPageHealth
from gitlab_evaluator_fixtures import evaluation_case
from gitlab_preparation_fixtures import put
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("saved", [False, True])
def test_seven_original_checks_and_repeat_read_leave_native_and_cas_unchanged(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    saved: bool,
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch, saved=saved) as c:
        p = c.source.preparation
        before = p.native.reader.calls
        blobs = tuple(sorted((node_path / "private-evidence/blobs").iterdir()))
        evaluator = gitlab_ssh_evaluator(c.selected)
        first = evaluator.evaluate(c.contract, p.store, guard())
        assert first.status == (
            "success" if saved else "failure"
        ) and first.reward == int(saved)
        assert (
            len(first.checks) == 7
            and first.contract_ref == c.contract.task_contract_ref
        )
        assert evaluator.evaluate(c.contract, p.store, guard()) == first
        assert (
            p.native.reader.calls == before
            and tuple(sorted((node_path / "private-evidence/blobs").iterdir())) == blobs
        )


@pytest.mark.parametrize(
    "missing",
    ["environment_ref", "browser_spec_ref", "before", "after", "page", "trace_ref"],
)
def test_missing_required_facts_stay_unknown_without_native_retry(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:
        selected = c.selected.model_copy(update={missing: None})
        before = c.source.preparation.native.reader.calls
        result = gitlab_ssh_evaluator(selected).evaluate(
            c.contract, c.source.preparation.store, guard()
        )
        assert result.status == "unknown" and result.reward is None
        assert all(x.status == "unknown" for x in result.checks)
        assert c.source.preparation.native.reader.calls == before


@pytest.mark.parametrize(
    "fault",
    [
        "site_config",
        "browser_parent",
        "page_request",
        "trace_context",
        "missing_stop",
        "corrupt_native",
        "old_page_schema",
        "same_capture",
    ],
)
def test_foreign_corrupt_or_incomplete_original_evidence_cannot_score_failure(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:
        p, selected = c.source.preparation, c.selected
        assert (
            selected.before is not None
            and selected.page is not None
            and selected.trace_ref is not None
        )
        original_page = selected.page
        if fault == "site_config":
            site_intent = SiteCaptureIntent.model_validate_json(
                p.store.read(selected.before.intent_ref)
            )
            pair = selected.before.model_copy(
                update={
                    "intent_ref": put(
                        p.store,
                        site_intent.model_copy(
                            update={"configuration_sha256": "f" * 64}
                        ),
                    )
                }
            )
            selected = selected.model_copy(update={"before": pair})
        elif fault == "page_request":
            page_intent = BrowserCaptureIntent.model_validate_json(
                p.store.read(original_page.intent_ref)
            )
            page_intent = page_intent.model_copy(
                update={
                    "request": page_intent.request.model_copy(
                        update={"observation_sha256": "f" * 64}
                    )
                }
            )
            selected = selected.model_copy(
                update={
                    "page": original_page.model_copy(
                        update={"intent_ref": put(p.store, page_intent)}
                    )
                }
            )
        elif fault == "trace_context":
            trace = c.trace.model_copy(
                update={
                    "scope": c.trace.scope.model_copy(update={"context_id": "foreign"})
                }
            )
            selected = selected.model_copy(update={"trace_ref": put(p.store, trace)})
        elif fault == "browser_parent":
            browser = c.browser.model_copy(
                update={
                    "slurm": c.browser.slurm.model_copy(
                        update={
                            "parent": c.browser.slurm.parent.model_copy(
                                update={
                                    "user_inode": c.browser.slurm.parent.user_inode
                                    + 1000
                                }
                            )
                        }
                    )
                }
            )
            selected = selected.model_copy(
                update={"browser_spec_ref": put(p.store, browser)}
            )
        elif fault == "missing_stop":
            (
                node_path / "private-evidence/blobs" / c.trace.stop_evidence_ref.sha256
            ).unlink()
        elif fault == "corrupt_native":
            assert p.native.task.snapshot is not None
            (
                node_path
                / "private-evidence/blobs"
                / p.native.task.snapshot.native_before.payload_ref.sha256
            ).write_bytes(b"{}")
        elif fault == "old_page_schema":
            returned = BrowserCaptureResult.model_validate_json(
                p.store.read(original_page.result_ref)
            )
            returned = returned.model_copy(
                update={
                    "private_result": returned.private_result.replace(
                        "gitlab-page-health/1", "gitlab-page-health/0"
                    )
                }
            )
            selected = selected.model_copy(
                update={
                    "page": original_page.model_copy(
                        update={"result_ref": put(p.store, returned)}
                    )
                }
            )
        else:
            selected = selected.model_copy(update={"after": selected.before})
        before = p.native.reader.calls
        result = gitlab_ssh_evaluator(selected).evaluate(c.contract, p.store, guard())
        assert result.status == "unknown" and result.reward is None
        assert p.native.reader.calls == before


@pytest.mark.parametrize(
    "fault", ["transport", "server_error", "missing_account", "login"]
)
def test_complete_page_negative_and_missing_transport_policy_remain_distinct(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:
        p, selected = c.source.preparation, c.selected
        assert selected.page is not None
        returned = BrowserCaptureResult.model_validate_json(
            p.store.read(selected.page.result_ref)
        )
        page = GitlabPageHealth.model_validate_json(returned.private_result)
        change: dict[str, object] = (
            {"http_status": None, "status_source": "unavailable"}
            if fault == "transport"
            else (
                {"http_status": 500, "error_page": True}
                if fault == "server_error"
                else {"account_id": None, "login_page": fault == "login"}
            )
        )
        page = GitlabPageHealth.model_validate({**page.model_dump(), **change})
        pair = selected.page.model_copy(
            update={
                "result_ref": put(
                    p.store,
                    returned.model_copy(
                        update={"private_result": page.model_dump_json()}
                    ),
                )
            }
        )
        result = gitlab_ssh_evaluator(
            selected.model_copy(update={"page": pair})
        ).evaluate(c.contract, p.store, guard())
        assert result.status == ("failure" if fault == "login" else "unknown")
        assert result.reward == (0 if fault == "login" else None)


@pytest.mark.parametrize("fault", ["scope", "family", "split", "requirements"])
def test_unsupported_contract_is_rejected_before_evidence_reads(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:
        contract = c.contract
        if fault == "scope":
            contract = contract.model_copy(update={"scope": "benchmark"})
        elif fault == "requirements":
            contract = contract.model_copy(
                update={"requirements": EvidenceRequirements()}
            )
        else:
            contract = contract.model_copy(
                update={
                    "identity": contract.identity.model_copy(
                        update={fault: "other" if fault == "family" else "test"}
                    )
                }
            )
        with pytest.raises(ValueError, match="Unsupported"):
            gitlab_ssh_evaluator(c.selected).evaluate(
                contract, c.source.preparation.store, guard()
            )


def test_cancellation_propagates_without_extra_native_capture(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:

        class Stopped:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "original-evaluation")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        before = c.source.preparation.native.reader.calls
        with pytest.raises(OperationStopped):
            gitlab_ssh_evaluator(c.selected).evaluate(
                c.contract, c.source.preparation.store, Stopped()
            )
        assert c.source.preparation.native.reader.calls == before
