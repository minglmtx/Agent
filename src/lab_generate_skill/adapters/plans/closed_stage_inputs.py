"""Publish exact private closed-stage facts; admission remains in the core gate."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Literal
from lab_generate_skill.domain.ended_stage_preparation import (
    EndedPreparationStageEvidence,
)
from lab_generate_skill.domain.closed_stage_acquisition import (
    ClosedPreRegistrationStageEvidence,
)

from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.stage_validation_admission import (
    ClosedPreAttemptStageEvidence,
)
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl


@dataclass(frozen=True)
class ClosedPriorStageInputs:
    objects: tuple[tuple[EvidenceRef, bytes], ...]
    references: tuple[EvidenceRef, ...]

    @property
    def authorization_schema(
        self,
    ) -> Literal[
        "task-stage-validation-authorization/2",
        "task-stage-validation-authorization/3",
        "task-stage-validation-authorization/4",
    ]:
        if any(
            r.content_schema == "ended-preparation-stage-evidence/1"
            for r in self.references
        ):
            return "task-stage-validation-authorization/4"
        return (
            "task-stage-validation-authorization/3"
            if any(
                r.content_schema == "closed-pre-registration-stage-evidence/1"
                for r in self.references
            )
            else "task-stage-validation-authorization/2"
        )

    def publish(
        self, store: EvidenceStore, control: OperationControl
    ) -> tuple[EvidenceRef, ...]:
        for ref, body in self.objects:
            control.checkpoint()
            require_complete_bytes(ref, body)
            metadata = EvidenceMetadata.model_validate(
                ref.model_dump(
                    include={"media_type", "content_schema", "visibility", "producer"}
                )
            )
            if store.put(body, metadata, control=control) != ref:
                raise ValueError(
                    "Closed-stage publication changed its original reference"
                )
        return self.references


def load_closed_prior_stage_inputs(
    path: Path | None,
    digest: str | None,
    workspace: Path,
    control: OperationControl,
) -> ClosedPriorStageInputs | None:
    """Validate bounded data before resource supply; missing selection stays v1."""
    if (path is None) != (digest is None):
        raise ValueError("Closed-stage input path and digest must be paired")
    if path is None:
        return None
    control.checkpoint()
    if path.resolve(strict=True) != path or not path.is_relative_to(workspace):
        raise ValueError("Canonical workspace closed-stage input required")
    if path.stat().st_size > 128 * 1024:
        raise ValueError("Closed-stage manifest exceeds its bounded read")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Closed-stage input changed")
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or set(data)
        != {
            "schema_version",
            "references",
            "closed_prior_stage_refs",
            "snapshots",
            "admission_or_model_grant",
        }
        or data["schema_version"] != "closed-prior-stage-publication/1"
        or data["admission_or_model_grant"] is not False
        or not isinstance(data["references"], list)
        or not 1 <= len(data["references"]) <= 1024
        or not isinstance(data["closed_prior_stage_refs"], list)
        or not 1 <= len(data["closed_prior_stage_refs"]) <= 128
    ):
        raise ValueError("Explicit closed-stage data-only publication required")
    refs = tuple(EvidenceRef.model_validate(v) for v in data["references"])
    reviews = tuple(
        EvidenceRef.model_validate(v) for v in data["closed_prior_stage_refs"]
    )
    if (
        len(set(refs)) != len(refs)
        or len({ref.sha256 for ref in refs}) != len(refs)
        or len(set(reviews)) != len(reviews)
        or not set(reviews) <= set(refs)
        or any(ref.visibility != "private" for ref in refs)
        or any(
            ref.content_schema
            not in (
                "closed-pre-attempt-stage-evidence/1",
                "closed-pre-registration-stage-evidence/1",
                "ended-preparation-stage-evidence/1",
            )
            for ref in reviews
        )
        or sum(ref.size_bytes for ref in refs) > 64 * 1024**2
    ):
        raise ValueError("Unique bounded private closed-stage references required")
    snapshots = Path(data["snapshots"])
    if (
        snapshots != path.parent / "snapshots"
        or snapshots.resolve(strict=True) != snapshots
    ):
        raise ValueError("Closed-stage snapshot directory changed")
    objects = []
    for ref in refs:
        control.checkpoint()
        item = snapshots / ref.sha256
        if item.is_symlink() or item.stat().st_size != ref.size_bytes:
            raise ValueError("Closed-stage snapshot size or path changed")
        body = item.read_bytes()
        require_complete_bytes(ref, body)
        objects.append((ref, body))
    bodies = dict(objects)
    for ref in reviews:
        selected: (
            ClosedPreAttemptStageEvidence
            | ClosedPreRegistrationStageEvidence
            | EndedPreparationStageEvidence
        )
        if ref.content_schema == "ended-preparation-stage-evidence/1":
            selected = EndedPreparationStageEvidence.model_validate_json(bodies[ref])
            required = {
                selected.site_resource_ref,
                selected.site_disposition_ref,
                selected.member_ref,
            }
            if selected.process_observation_ref is not None:
                required.add(selected.process_observation_ref)
            if not required <= set(refs):
                raise ValueError("Publication omitted original ended-preparation facts")
        elif ref.content_schema == "closed-pre-registration-stage-evidence/1":
            selected = ClosedPreRegistrationStageEvidence.model_validate_json(
                bodies[ref]
            )
            if not {
                selected.site_spec_ref,
                selected.site_adapter_ref,
                selected.traceback_ref,
                selected.member_ref,
            } <= set(refs):
                raise ValueError(
                    "Closed-stage publication omitted original acquisition facts"
                )
        else:
            selected = ClosedPreAttemptStageEvidence.model_validate_json(bodies[ref])
        if (
            not isinstance(selected, EndedPreparationStageEvidence)
            and selected.diagnostic_ref not in refs
        ):
            raise ValueError("Publication omitted the original closed-run diagnostic")
        if not {
            selected.claim_ref,
            selected.source_ref,
            selected.run_ref,
            selected.actor_resource_ref,
            selected.session_ref,
            selected.accounting_ref,
        } <= set(refs):
            raise ValueError("Closed-stage publication omitted a selected dependency")
    control.checkpoint()
    return ClosedPriorStageInputs(tuple(objects), reviews)
