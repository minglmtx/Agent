"""Original Group source contract through current evaluator; no live site effects."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.gitlab_group_evaluation import gitlab_group_evaluator
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.evidence import EvidenceRequirements
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.sites.gitlab.evidence_schema import (
    GroupEvidence,
    GitlabPageHealth,
)
from gitlab_group_evaluator_fixtures import evaluation_case
from gitlab_group_preparation_fixtures import put
from source_review_records import ReadOnlyEvidence
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("projects_changed", [False, True])
def test_complete_original_goal_and_raw_project_guard_priority_readonly_repeat(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    saved: bool,
    projects_changed: bool,
) -> None:
    with evaluation_case(
        tmp_path, node_path, monkeypatch, saved=saved, projects_changed=projects_changed
    ) as c:
        p = c.source.preparation
        before = len(p.native.sql.calls)
        blobs = tuple(sorted((node_path / "private-evidence/blobs").iterdir()))
        reader = ReadOnlyEvidence(node_path / "private-evidence")
        evaluator = gitlab_group_evaluator(c.selected)
        first = evaluator.evaluate(c.contract, reader, guard())
        expected = (
            "unknown"
            if saved and projects_changed
            else "success" if saved else "failure"
        )
        assert first.status == expected and first.reward == (
            None if expected == "unknown" else int(saved)
        )
        checks = {check.name: check.status for check in first.checks}
        assert checks["selected_projects_preserved"] == (
            "fail" if projects_changed else "pass"
        )
        assert checks["one_group_saved"] == ("pass" if saved else "fail")
        if projects_changed:
            assert first.reason_code == (
                "PROTECTED_PROJECTS_CHANGED"
                if saved
                else "GOAL_FAILED_AND_PROTECTED_PROJECTS_CHANGED"
            )
        assert evaluator.evaluate(c.contract, reader, guard()) == first
        assert len(p.native.sql.calls) == before
        assert tuple(sorted((node_path / "private-evidence/blobs").iterdir())) == blobs


@pytest.mark.parametrize(
    "missing",
    ["environment_ref", "browser_spec_ref", "before", "after", "page", "trace_ref"],
)
def test_missing_required_fact_stays_unknown_without_recapture(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:
        p = c.source.preparation
        before = len(p.native.sql.calls)
        result = gitlab_group_evaluator(
            c.selected.model_copy(update={missing: None})
        ).evaluate(c.contract, p.store, guard())
        assert result.status == "unknown" and result.reward is None
        assert all(check.status == "unknown" for check in result.checks)
        assert len(p.native.sql.calls) == before


@pytest.mark.parametrize(
    "fault",
    [
        "site-config",
        "page-request",
        "same-capture",
        "browser-parent",
        "missing-stop",
        "profile",
        "native-schema",
        "initializer-account",
    ],
)
def test_foreign_partial_or_changed_context_cannot_score_a_failure(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:
        p, selected = c.source.preparation, c.selected
        assert selected.before and selected.page
        original_page = selected.page
        if fault == "site-config":
            intent = SiteCaptureIntent.model_validate_json(
                p.store.read(selected.before.intent_ref, guard())
            )
            selected = selected.model_copy(
                update={
                    "before": selected.before.model_copy(
                        update={
                            "intent_ref": put(
                                p.store,
                                intent.model_copy(
                                    update={"configuration_sha256": "f" * 64}
                                ),
                            )
                        }
                    )
                }
            )
        elif fault == "page-request":
            page_intent = BrowserCaptureIntent.model_validate_json(
                p.store.read(original_page.intent_ref, guard())
            )
            selected = selected.model_copy(
                update={
                    "page": original_page.model_copy(
                        update={
                            "intent_ref": put(
                                p.store,
                                page_intent.model_copy(
                                    update={
                                        "request": page_intent.request.model_copy(
                                            update={"observation_sha256": "f" * 64}
                                        )
                                    }
                                ),
                            )
                        }
                    )
                }
            )
        elif fault == "same-capture":
            selected = selected.model_copy(update={"after": selected.before})
        elif fault in ("browser-parent", "initializer-account"):
            browser = c.browser
            if fault == "browser-parent":
                browser = browser.model_copy(
                    update={
                        "slurm": browser.slurm.model_copy(
                            update={
                                "parent": browser.slurm.parent.model_copy(
                                    update={
                                        "user_inode": browser.slurm.parent.user_inode
                                        + 1000
                                    }
                                )
                            }
                        )
                    }
                )
            else:
                initialization = browser.configuration.initialization
                assert initialization is not None
                browser = browser.model_copy(
                    update={
                        "configuration": browser.configuration.model_copy(
                            update={
                                "initialization": initialization.model_copy(
                                    update={"native_account_id": 2}
                                )
                            }
                        )
                    }
                )
            selected = selected.model_copy(
                update={"browser_spec_ref": put(p.store, browser)}
            )
        elif fault == "missing-stop":
            (
                node_path / "private-evidence/blobs" / c.trace.stop_evidence_ref.sha256
            ).unlink()
        elif fault == "profile":
            from lab_generate_skill.domain.native_private_json import (
                GITLAB_PRIVATE_JSON,
            )

            config = c.source.site.configuration
            profile = config.private_evidence
            assert profile is not None
            changed = c.source.site.model_copy(
                update={
                    "configuration": config.model_copy(
                        update={
                            "private_evidence": profile.model_copy(
                                update={"profile": GITLAB_PRIVATE_JSON}
                            )
                        }
                    )
                }
            )
            selected = selected.model_copy(
                update={
                    "environment_ref": put(
                        p.store,
                        c.source.environment.model_copy(
                            update={"site_spec_ref": put(p.store, changed)}
                        ),
                    )
                }
            )
        else:
            assert p.native.task.snapshot is not None
            (
                node_path
                / "private-evidence/blobs"
                / p.native.task.snapshot.native_before.payload_ref.sha256
            ).write_bytes(b"{}")
        before = len(p.native.sql.calls)
        result = gitlab_group_evaluator(selected).evaluate(c.contract, p.store, guard())
        assert result.status == "unknown" and result.reward is None
        assert len(p.native.sql.calls) == before


@pytest.mark.parametrize("fault", ["transport", "server-error", "login", "404"])
def test_native_document_transport_unknown_is_distinct_from_real_goal_failure(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:
        p, selected = c.source.preparation, c.selected
        assert selected.page is not None
        result = BrowserCaptureResult.model_validate_json(
            p.store.read(selected.page.result_ref, guard())
        )
        page = GitlabPageHealth.model_validate_json(result.private_result)
        change: dict[str, object] = (
            {"http_status": None, "status_source": "unavailable"}
            if fault == "transport"
            else (
                {"http_status": 500, "error_page": True}
                if fault == "server-error"
                else (
                    {"http_status": 404, "error_page": True}
                    if fault == "404"
                    else {"account_id": None, "login_page": True}
                )
            )
        )
        page = GitlabPageHealth.model_validate({**page.model_dump(), **change})
        pair = selected.page.model_copy(
            update={
                "result_ref": put(
                    p.store,
                    result.model_copy(
                        update={"private_result": page.model_dump_json()}
                    ),
                )
            }
        )
        before = len(p.native.sql.calls)
        evaluation = gitlab_group_evaluator(
            selected.model_copy(update={"page": pair})
        ).evaluate(c.contract, p.store, guard())
        assert evaluation.status == (
            "failure" if fault in ("login", "404") else "unknown"
        )
        assert evaluation.reward == (0 if fault in ("login", "404") else None)
        assert len(p.native.sql.calls) == before


@pytest.mark.parametrize("fault", ["scope", "family", "split", "requirements"])
def test_unsupported_contract_rejected_before_any_evidence_read(
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

        class NoReads:
            def read(self, ref: Any, control: Any = None) -> bytes:
                raise AssertionError(
                    "Unsupported input must be rejected before reading"
                )

        with pytest.raises(ValueError, match="Unsupported"):
            gitlab_group_evaluator(c.selected).evaluate(contract, NoReads(), guard())


def test_all_absent_and_cancelled_evaluation_never_captures_again(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:
        p = c.source.preparation
        selected = GroupEvidence(
            environment_ref=None,
            browser_spec_ref=None,
            before=None,
            after=None,
            page=None,
            trace_ref=None,
        )
        before = len(p.native.sql.calls)
        result = gitlab_group_evaluator(selected).evaluate(c.contract, p.store, guard())
        assert result.status == "unknown" and result.reward is None
        with pytest.raises(OperationStopped):
            gitlab_group_evaluator(c.selected).evaluate(c.contract, p.store, guard(-1))
        assert len(p.native.sql.calls) == before


@pytest.mark.parametrize(
    "bad", [None, [], "", 0, {"schema_version": "gitlab-group-evidence/0"}]
)
def test_illegal_or_wrong_type_selection_is_rejected(bad: Any) -> None:
    with pytest.raises(ValueError):
        GroupEvidence.model_validate(bad)
