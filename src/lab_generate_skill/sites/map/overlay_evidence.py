"""Selected original predicates over previously verified complete terminal/DB reads.

No dispatch or live browser/DB access. Final evaluator must also bind the sealed
Actor trace and final state inspection; these predicates alone are not admission.
"""

from typing import Any
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from .terminal_evidence import TerminalMapEvidence
from .terminal_requests import reference_candidates
from .reference_evidence import MapReferenceRead
from .native_compare import compare_database
from .state_rules import object_json
from .page_health import MapPageHealth
from .overlay_rules import overlay_rows, selected_transition_checks


def original_overlay_checks(
    terminal: TerminalMapEvidence,
    references: tuple[MapReferenceRead, ...],
    page: MapPageHealth,
    *,
    served: bool,
    control: OperationControl,
) -> dict[str, bool]:
    candidates = reference_candidates(terminal, control).selected
    if (
        type(references) is not tuple
        or len(references) != len(candidates)
        or any(not isinstance(r, MapReferenceRead) for r in references)
    ):
        raise EvidenceIntegrityError(
            "Every original eligible response needs exactly one independent reference"
        )
    results = []
    for candidate, reference in zip(candidates, references, strict=True):
        artifact = reference.artifact
        selected = artifact.selected
        if (
            selected.terminal_handle != terminal.publication.handle
            or selected.request_index != candidate.index
            or selected.bounds != candidate.bounds
            or selected.response_kind != candidate.response_kind
            or selected.payload != candidate.payload
            or selected.records_sha256 != candidate.records_sha256
            or reference.payload != candidate.body
        ):
            raise EvidenceIntegrityError(
                "Selected original DB/reference response binding differs"
            )
        # Recompute, retaining pure comparison provenance flags unchanged.
        comparison = compare_database(
            reference.payload,
            selected.bounds,
            object_json(reference.database),
            response_kind=selected.response_kind,
        )
        if comparison != reference.comparison:
            raise EvidenceIntegrityError("Original full database comparison changed")
        results.append(comparison["passed"])
    facts = [p["facts"] for p in terminal.pages]
    if not facts or any(
        type(f) is not dict
        or set(f) != {"surface", "route"}
        or type(f["surface"]) is not dict
        or type(f["route"]) is not dict
        for f in facts
    ):
        raise EvidenceIntegrityError("Original complete page/route facts missing")
    baseline = facts[0]["surface"]
    for f in facts:
        if f["surface"].get("map_visible") is True:
            rows = overlay_rows(f["surface"])
            if "Map Data" in rows and rows["Map Data"]["checked"] is False:
                baseline = f["surface"]
                break
    origin = terminal.initial.browser.configuration.map_inputs
    if origin is None:
        raise EvidenceIntegrityError("Original Map inputs missing")
    from urllib.parse import urlsplit

    url = urlsplit(terminal.initial.prepared.public_task.start_url)
    judgments: list[dict[str, Any]] = []
    for matched in results or [False]:
        checks = selected_transition_checks(
            baseline,
            facts[-1]["surface"],
            url.scheme + "://" + url.netloc,
            initial_route=facts[0]["route"],
            terminal_route=facts[-1]["route"],
            response_matches=matched,
            served=served,
            page=page,
        )
        judgments.append(checks)
    control.checkpoint()
    return next((j for j in reversed(judgments) if all(j.values())), judgments[-1])
