"""Strict selected-evidence boundary and truthful unified Evaluation outcomes."""

from typing import Any, cast
import pytest
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.errors import EvidenceNotFound, OperationStopped
from lab_generate_skill.domain.errors import IncompleteAnswerEvidence
from lab_generate_skill.evaluators.map.native_overlay import (
    CHECKS,
    REQUIREMENTS,
    OverlayEvaluator,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.evidence_schema import (
    MapCapturePair,
    MapOverlayEvidence,
)
from lab_generate_skill.sites.map.tasks.overlay_spec import SOURCE
from test_core_contracts import reference
from test_slurm_commands import guard
from evidence_control_fixtures import EvidenceFixtureStore
from pathlib import Path


def selected() -> MapOverlayEvidence:
    return MapOverlayEvidence(
        environment_ref=reference("private", "environment-selection/1"),
        terminal_ref=None,
        page=None,
        references=(),
        final_guard=None,
        browser_closure_ref=None,
        trace_ref=None,
        trace_snapshot_ref=None,
    )


def contract() -> EvaluationContract:
    return EvaluationContract(
        identity=TaskIdentity(
            site="map",
            family="native_route_map_data",
            source_task_id=SOURCE,
            task_id=SOURCE,
            split="train",
            contract_version=1,
        ),
        attempt_id="attempt",
        task_contract_ref=reference("private", "task-binding/1"),
        public_task_ref=reference("public", "public-task/1"),
        completion_spec_ref=reference("private", "map-native-overlay/1"),
        requirements=REQUIREMENTS,
        scope="engineering",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"references": []},
        {"references": "bad"},
        {"references": (None,)},
        {"trace_ref": reference("public", "interaction-trace/1")},
        {"trace_ref": reference("private", "trace-journal-snapshot/1")},
        {"terminal_ref": ""},
        {"page": {}},
        {"extra": True},
    ],
)
def test_evidence_strict_types_and_schemas(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        MapOverlayEvidence.model_validate({**selected().model_dump(), **change})


def test_evidence_exact_pair_kind_and_duplicate_rejected() -> None:
    site = MapCapturePair(
        intent_ref=reference("private", "site-capture-intent/2"),
        result_ref=reference("private", "site-task-result/1"),
    )
    browser = MapCapturePair(
        intent_ref=reference("private", "browser-capture-intent/1"),
        result_ref=reference("private", "browser-capture-result/1"),
    )
    for change in (
        {"references": (site, site)},
        {"references": (browser,)},
        {"final_guard": browser},
        {"page": site},
    ):
        with pytest.raises(ValueError):
            MapOverlayEvidence.model_validate(selected().model_copy(update=change))
    with pytest.raises(ValueError):
        MapCapturePair(intent_ref=site.intent_ref, result_ref=browser.result_ref)
    assert selected().references == ()
    assert selected().model_copy(update={"references": None}).references is None


@pytest.mark.parametrize(
    "mode",
    [
        "success",
        "failure",
        "missing",
        "partial",
        "invalid",
        "wrong-type",
        "io",
        "cancel",
    ],
)
def test_truthful_evaluation_and_no_hidden_runtime_error(
    tmp_path: Path, mode: str
) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    store = EvidenceFixtureStore(root)

    def load(
        contract: EvaluationContract,
        selected: MapOverlayEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> dict[str, bool]:
        if mode == "missing":
            raise EvidenceNotFound("Missing original capture")
        if mode == "partial":
            raise IncompleteAnswerEvidence("Original uncertain Actor")
        if mode == "io":
            raise OSError("Original unknown file transport")
        if mode == "cancel":
            guard(-1).checkpoint()
        values: Any = dict.fromkeys(CHECKS, True)
        if mode == "failure":
            values[CHECKS[3]] = False
        if mode == "invalid":
            values.pop(CHECKS[3])
        if mode == "wrong-type":
            values[CHECKS[3]] = 1
        return cast(dict[str, bool], values)

    evaluator = OverlayEvaluator(selected(), load)
    if mode in ("io", "cancel"):
        with pytest.raises(OSError if mode == "io" else OperationStopped):
            evaluator.evaluate(contract(), store, guard())
        return
    result = evaluator.evaluate(contract(), store, guard())
    assert result.status == (mode if mode in ("success", "failure") else "unknown")
    assert result.reward == ({"success": 1, "failure": 0}.get(mode))
    assert tuple(c.name for c in result.checks) == CHECKS
    assert evaluator.evaluate(contract(), store, guard()) == result
    for change in (
        {"scope": "benchmark"},
        {
            "identity": contract().identity.model_copy(
                update={"source_task_id": "other"}
            )
        },
        {"attempt_id": ""},
    ):
        with pytest.raises(ValueError):
            evaluator.evaluate(contract().model_copy(update=change), store, guard())
