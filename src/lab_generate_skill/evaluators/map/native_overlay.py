"""Unified engineering Evaluation; unavailable/uncertain facts retain null reward."""

from typing import Protocol, Literal
from lab_generate_skill.domain.evaluation import (
    EvaluationContract,
    Evaluation,
    CheckResult,
)
from lab_generate_skill.domain.evidence import EvidenceRequirement, EvidenceRequirements
from lab_generate_skill.domain.errors import EvidenceError, OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.errors import IncompleteAnswerEvidence
from lab_generate_skill.sites.map.evidence_schema import MapOverlayEvidence, SOURCE

CHECKS = (
    "valid_local_native_map",
    "actual_supported_local_layer_changed",
    "native_selected_control_and_layer_code_agree",
    "actual_local_response_valid",
    "native_ajax_and_warning_settled",
    "original_current_area_preserved",
    "original_requested_native_route_preserved",
    "actual_native_leaflet_overlay_active",
    "actual_reviewed_frontend_served",
    "valid_terminal_document",
    "original_complete_persistent_state_unchanged",
)
REQUIREMENTS = EvidenceRequirements(
    facts=tuple(
        EvidenceRequirement(name=name, content_schema=schema, visibility="private")
        for name, schema in (
            ("environment", "environment-selection/1"),
            ("terminal", "map-terminal-selection/1"),
            ("final_page", "browser-capture-result/1"),
            ("independent_database", "site-task-result/1"),
            ("final_guard", "site-task-result/1"),
            ("browser_closed", "closure-receipt/1"),
            ("sealed_trace", "interaction-trace/1"),
            ("original_trace_journal", "trace-journal-snapshot/1"),
        )
    )
)


class MapFactsLoader(Protocol):
    def __call__(
        self,
        contract: EvaluationContract,
        selected: MapOverlayEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> dict[str, bool]: ...


class OverlayEvaluator:
    def __init__(self, selected: MapOverlayEvidence, loader: MapFactsLoader) -> None:
        self.selected = MapOverlayEvidence.model_validate(selected)
        self.loader = loader

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        identity = contract.identity
        if (
            identity.site,
            identity.family,
            identity.source_task_id,
            identity.task_id,
            identity.contract_version,
            identity.split,
            contract.scope,
        ) != (
            "map",
            "native_route_map_data",
            SOURCE,
            SOURCE,
            1,
            "train",
            "engineering",
        ) or contract.requirements != REQUIREMENTS:
            raise ValueError(
                "Unsupported original selected engineering Map evaluation contract"
            )
        return REQUIREMENTS

    def evaluate(
        self,
        contract: EvaluationContract,
        evidence: EvidenceReader,
        control: OperationControl,
    ) -> Evaluation:
        contract = EvaluationContract.model_validate(contract)
        self.requirements(contract)
        control.checkpoint()
        refs = self.selected.evidence_refs()
        values: dict[str, bool] | None = None
        reason = "INVALID_CAPTURE_EVIDENCE"
        try:
            values = self.loader(contract, self.selected, evidence, control)
            if (
                type(values) is not dict
                or tuple(values) != CHECKS
                or any(type(v) is not bool for v in values.values())
            ):
                values = None
                raise ValueError("Complete original Map checks required")
        except (EvidenceError, OwnershipConflict) as error:
            values, reason = None, error.reason_code
        except IncompleteAnswerEvidence:
            values, reason = None, "INCOMPLETE_ACTOR_EXECUTION"
        except ValueError:
            values, reason = None, "INVALID_CAPTURE_EVIDENCE"
        control.checkpoint()
        status: Literal["unknown", "success", "failure"] = (
            "unknown"
            if values is None
            else "success" if all(values.values()) else "failure"
        )
        reason = (
            reason
            if values is None
            else (
                "ORIGINAL_MAP_MATCH" if status == "success" else "ORIGINAL_MAP_MISMATCH"
            )
        )
        return Evaluation(
            identity=contract.identity,
            attempt_id=contract.attempt_id,
            contract_ref=contract.task_contract_ref,
            evaluator_id="map-native-overlay",
            evaluator_version="map-native-overlay-v1",
            status=status,
            reward=None if values is None else int(status == "success"),
            checks=tuple(
                CheckResult(
                    name=name,
                    status=(
                        "unknown"
                        if values is None
                        else "pass" if values[name] else "fail"
                    ),
                    reason_code=(
                        reason
                        if values is None
                        else "MATCH" if values[name] else "MISMATCH"
                    ),
                    evidence=refs,
                )
                for name in CHECKS
            ),
            reason_code=reason,
            evidence=refs,
        )
