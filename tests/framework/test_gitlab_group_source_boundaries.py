"""Group source branch refusals on original typed records, with no live grant."""

from datetime import timedelta
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.gitlab_group_source import GroupSourceSelection
from lab_generate_skill.bootstrap.gitlab_group_closed_preparation import (
    closed_group_preparations,
)
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.native_private_json import GITLAB_PRIVATE_JSON
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.sites.gitlab.tasks.group_native_request import (
    GroupNativeRequestChecks,
)
from lab_generate_skill.sites.gitlab.tasks.group_source_initial import (
    CapturedGroupInitialChecks,
)
from lab_generate_skill.sites.gitlab.evidence_schema import GitlabPageHealth
from gitlab_group_preparation_fixtures import prepared_case
from gitlab_group_source_fixtures import group_source_unit_case
from test_gitlab_group_source_composition import contracts_for
from test_gitlab_group_complete_starts import original
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize("native", [None, b"", "", 0, True, {}, []])
def test_Group_selection_empty_or_wrong_bytes_refused(native: Any) -> None:
    _, _, public = original("e4d658cfba6588f6a386")
    with pytest.raises((ValueError, TypeError)):
        GroupSourceSelection(native, public)


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "binding",
        "coverage",
        "environment",
        "profile",
        "missing-snapshot",
        "snapshot-request",
        "snapshot-bytes",
        "private-size",
    ],
)
def test_Group_native_full_binding_recovery_and_snapshot_rules_before_any_effect(
    tmp_path: Path, node_path: Path, fault: str
) -> None:
    with prepared_case(tmp_path, node_path) as c:
        cfg, request, binding, recovery = (
            c.configuration,
            c.inputs.request,
            c.inputs.binding,
            c.inputs.recovery,
        )
        environment = RecoveryPlan.model_validate_json(
            c.store.read(cfg.token.recovery_ref, guard())
        )
        assert c.native.task.snapshot is not None
        snapshot: bytes | None = c.native.task.snapshot.model_dump_json().encode()
        saved = c.native.task.snapshot.request
        calls = len(c.native.sql.calls)
        if fault == "binding":
            binding = binding.model_copy(
                update={
                    "identity": binding.identity.model_copy(
                        update={"source_task_id": "foreign"}
                    )
                }
            )
        elif fault == "coverage":
            recovery = recovery.model_copy(update={"state_coverage": ("incomplete",)})
        elif fault == "environment":
            environment = environment.model_copy(
                update={"restore_component_id": "foreign"}
            )
        elif fault == "profile":
            assert cfg.private_evidence is not None
            cfg = cfg.model_copy(
                update={
                    "private_evidence": cfg.private_evidence.model_copy(
                        update={"profile": GITLAB_PRIVATE_JSON}
                    )
                }
            )
        elif fault == "missing-snapshot":
            snapshot = None
        elif fault == "snapshot-request":
            saved = saved.model_copy(
                update={
                    "operation": saved.operation.model_copy(
                        update={"operation_id": "foreign"}
                    )
                }
            )
        elif fault == "snapshot-bytes":
            assert snapshot is not None
            snapshot += b"\n"
        elif fault == "private-size":
            binding = binding.model_copy(
                update={
                    "private_spec_ref": binding.private_spec_ref.model_copy(
                        update={"size_bytes": binding.private_spec_ref.size_bytes + 1}
                    )
                }
            )
        check = GroupNativeRequestChecks()
        if fault == "none":
            check.verify_inputs(
                cfg, request, binding, recovery, environment, snapshot, saved, guard()
            )
            check.verify_inputs(
                cfg, request, binding, recovery, environment, snapshot, saved, guard()
            )
        else:
            with pytest.raises((ValueError, OwnershipConflict)):
                check.verify_inputs(
                    cfg,
                    request,
                    binding,
                    recovery,
                    environment,
                    snapshot,
                    saved,
                    guard(),
                )
        assert len(c.native.sql.calls) == calls


def test_Group_initial_capture_foreign_account_scope_and_incomplete_health_refused_without_new_browser(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = group_source_unit_case(
        tmp_path, node_path, monkeypatch, contracts_for("e4d658cfba6588f6a386"), "none"
    )
    facts, store = c.facts, c.site.evidence
    preparations = closed_group_preparations(
        facts.baseline_inputs, facts.site, facts.browser, store, c.site.controls
    )
    op = facts.baseline_inputs.preparation.operation.cleanup(
        "group-capture-read", now=c.site.clock.utcnow(), seconds=120
    )
    initial = InitialObservationReader(store, preparations).load(
        facts.initial, op, guard(120)
    )
    intent = BrowserCaptureIntent.model_validate_json(
        store.read(facts.capture_intent_ref, guard())
    )
    result = BrowserCaptureResult.model_validate_json(
        store.read(facts.capture_result_ref, guard())
    )
    assert (
        CapturedGroupInitialChecks(
            store, facts.capture_intent_ref, facts.capture_result_ref
        )
        .check(initial, guard())
        .status
        == "pass"
    )
    native = c.site.channels[0].engine.primitive
    calls = len(native.sql.calls)
    for fault in (
        "login",
        "error",
        "account",
        "url",
        "status",
        "scope",
        "configuration",
        "result-digest",
        "timestamp",
    ):
        chosen_intent, chosen_result = intent, result
        page = GitlabPageHealth.model_validate_json(result.private_result)
        if fault in ("login", "error", "account", "url", "status"):
            changes: dict[str, object] = (
                {"login_page": True, "account_id": None}
                if fault == "login"
                else (
                    {"error_page": True}
                    if fault == "error"
                    else (
                        {"account_id": 2}
                        if fault == "account"
                        else (
                            {"url": page.url + "/foreign"}
                            if fault == "url"
                            else {"http_status": None, "status_source": "unavailable"}
                        )
                    )
                )
            )
            page = GitlabPageHealth.model_validate(page.model_copy(update=changes))
            chosen_result = result.model_copy(
                update={"private_result": page.model_dump_json()}
            )
        elif fault == "scope":
            chosen_intent = intent.model_copy(
                update={
                    "request": intent.request.model_copy(
                        update={
                            "scope": intent.request.scope.model_copy(
                                update={"context_id": "foreign"}
                            )
                        }
                    )
                }
            )
        elif fault == "configuration":
            chosen_intent = intent.model_copy(update={"configuration_sha256": "0" * 64})
        elif fault == "result-digest":
            chosen_result = result.model_copy(update={"request_sha256": "0" * 64})
        elif fault == "timestamp":
            chosen_result = result.model_copy(
                update={
                    "captured_at": initial.observation.record.captured_at
                    - timedelta(microseconds=1)
                }
            )
        checker = CapturedGroupInitialChecks(
            store, put(store, chosen_intent), put(store, chosen_result)
        )
        with pytest.raises(EvidenceIntegrityError):
            checker.check(initial, guard())
    assert len(native.sql.calls) == calls
