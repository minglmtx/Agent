"""Typed contract/status boundaries; no site/model/source authority or requests."""

from dataclasses import replace
from pathlib import Path
from typing import Any, cast, Literal
import pytest
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    IncompleteAnswerEvidence,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.evaluators.map.navigation import (
    NavigationEvaluator,
    REQUIREMENTS,
    PAGE_CHECKS,
)
from lab_generate_skill.sites.map.evidence_schema import (
    MapNavigationEvidence,
    NavigationOutcome,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from map_navigation_fixtures import navigation_case
from map_navigation_browser_fixtures import CancelledControl
from test_core_contracts import reference
from test_slurm_commands import guard
from test_dependency_boundaries import (
    project_imports,
    check_evaluator_import,
    check_site_import,
)


class NoReads:
    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        raise AssertionError("Pure loader double never reads or performs business I/O")


class Loader:
    def __init__(self, value: Any) -> None:
        self.value, self.calls = value, 0

    def __call__(
        self,
        contract: EvaluationContract,
        selected: MapNavigationEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> NavigationOutcome:
        self.calls += 1
        if isinstance(self.value, Exception):
            raise self.value
        return cast(NavigationOutcome, self.value)


def declared() -> EvaluationContract:
    return EvaluationContract(
        identity=navigation_case().public.identity,
        attempt_id="attempt",
        task_contract_ref=reference(content_schema="task-binding/1"),
        public_task_ref=reference("public", "public-task/1"),
        completion_spec_ref=reference(content_schema="map-navigation-spec/1"),
        requirements=REQUIREMENTS,
        scope="engineering",
    )


def evidence() -> MapNavigationEvidence:
    return MapNavigationEvidence(
        environment_ref=reference(content_schema="environment-selection/1"),
        terminal_ref=reference(content_schema="map-navigation-terminal-selection/1"),
        final_guard=None,
        browser_closure_ref=reference(content_schema="closure-receipt/1"),
    )


@pytest.mark.parametrize("status", ["success", "failure", "unknown"])
def test_original_status_reward_checks_and_repeated_read(
    status: Literal["success", "failure", "unknown"],
) -> None:
    checks = (
        ()
        if status == "unknown"
        else tuple((n, status == "success" or n != "target_path") for n in PAGE_CHECKS)
    )
    value = NavigationOutcome(
        status, {"success": 1.0, "failure": 0.0, "unknown": None}[status], checks, None
    )
    loader = Loader(value)
    e = NavigationEvaluator(evidence(), loader)
    result = e.evaluate(declared(), NoReads(), guard(30))
    assert (
        result.status == status
        and result.reward == {"success": 1, "failure": 0, "unknown": None}[status]
    )
    assert e.evaluate(declared(), NoReads(), guard(30)) == result and loader.calls == 2


@pytest.mark.parametrize(
    "change",
    [
        {"checks": None},
        {"checks": {}},
        {"checks": (("correct_site", None),)},
        {"checks": (("correct_site", True), ("correct_site", True))},
        {"checks": (("invented", True),)},
        {"checks": ()},
        {"reward": True},
        {"reward": 0.0},
        {"reward": float("nan")},
        {"status": "other"},
        {"version": "other"},
        {"selected_records_unchanged": False},
        {"selected_records_unchanged": 1},
        {"state_change_requires_review": True},
    ],
)
def test_invalid_loader_facts_stay_unknown(change: dict[str, Any]) -> None:
    normal = NavigationOutcome(
        "success", 1.0, tuple((n, True) for n in PAGE_CHECKS), None
    )
    loader = Loader(replace(normal, **change))
    e = NavigationEvaluator(evidence(), loader)
    result = e.evaluate(declared(), NoReads(), guard(30))
    assert result.status == "unknown" and result.reward is None


@pytest.mark.parametrize(
    "error",
    [
        EvidenceNotFound("missing"),
        OwnershipConflict("foreign"),
        IncompleteAnswerEvidence("unknown"),
    ],
)
def test_missing_or_incomplete_execution_is_not_task_failure(error: Exception) -> None:
    result = NavigationEvaluator(evidence(), Loader(error)).evaluate(
        declared(), NoReads(), guard(30)
    )
    assert result.status == "unknown" and result.reward is None


def test_cancel_before_loader_and_foreign_contract_rejected() -> None:
    loader = Loader(None)
    e = NavigationEvaluator(evidence(), loader)
    with pytest.raises(OperationStopped):
        e.evaluate(declared(), NoReads(), CancelledControl())
    for identity in (
        declared().identity.model_copy(update={"site": "reddit"}),
        declared().identity.model_copy(
            update={"source_task_id": "058c211ed6572633b8e3"}
        ),
        declared().identity.model_copy(update={"split": "test"}),
    ):
        with pytest.raises(ValueError):
            e.requirements(declared().model_copy(update={"identity": identity}))
    assert loader.calls == 0


@pytest.mark.parametrize("invalid", [None, "", 1, [], {}])
def test_empty_or_wrong_typed_selection_is_not_admitted(invalid: Any) -> None:
    with pytest.raises(ValueError):
        MapNavigationEvidence.model_validate(invalid)


def test_current_navigation_changed_paths_obey_original_layer_boundaries() -> None:
    root = Path(__file__).resolve().parents[2] / "src/lab_generate_skill"
    allowed = {
        "sites": {"domain", "ports", "policies", "task_families", "sites"},
        "evaluators": {
            "domain",
            "ports",
            "policies",
            "task_families",
            "evaluators",
            "sites",
        },
        "bootstrap": {
            "domain",
            "ports",
            "policies",
            "adapters",
            "runtime",
            "application",
            "registry",
            "release",
            "generator",
            "actor",
            "sites",
            "bootstrap",
            "evaluators",
        },
    }
    for name in (
        "sites/map/evidence_schema.py",
        "sites/map/navigation_evaluation_reads.py",
        "evaluators/map/navigation.py",
        "bootstrap/map_navigation_evaluation.py",
    ):
        layer = name.split("/")[0]
        package = "lab_generate_skill." + name.rsplit("/", 1)[0].replace("/", ".")
        for imported in project_imports((root / name).read_text(), package):
            assert imported.split(".")[1] in allowed[layer], (name, imported)
            if layer == "evaluators":
                check_evaluator_import("map", imported)
            elif layer == "sites":
                check_site_import("map", imported)
