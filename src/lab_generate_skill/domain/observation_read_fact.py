"""Original same-snapshot read outcome; engineering return is not understanding."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .errors import OwnershipConflict
from .evidence import EvidenceRef
from .observation_read import ObservationReadRequest
from .observation_read_progress import ObservationReadRecord
from .state_scope import StateFact, private_state_ref
from .validation import Contract, Identifier


class ObservationReadFact(StateFact):
    schema_version: Literal["observation-read-fact/1"] = "observation-read-fact/1"
    generation_id: Identifier
    request: ObservationReadRequest
    outcome: Literal["returned", "failed", "uncertain", "returned_unconfirmed"]
    result: ObservationReadRecord | None
    failure_ref: EvidenceRef | None

    @model_validator(mode="after")
    def original_read_return(self) -> Self:
        if self.request.snapshot.scope != self.scope:
            raise OwnershipConflict(
                "Read outcome changed its original task/snapshot scope"
            )
        known = self.outcome in ("returned", "returned_unconfirmed")
        if known != (self.result is not None):
            raise ValueError(
                "Known returned reading requires its exact public result/count facts"
            )
        if self.result is not None and self.result.request != self.request:
            raise OwnershipConflict("Read result changed its original request/options")
        if (self.outcome == "returned") != (self.failure_ref is None):
            raise ValueError("Only a confirmed read returns without failure evidence")
        if self.failure_ref is not None:
            private_state_ref(self.failure_ref, "observation-read-failure/1")
        return self


class ObservationReadFailure(Contract):
    schema_version: Literal["observation-read-failure/1"] = "observation-read-failure/1"
    generation_id: Identifier
    request: ObservationReadRequest
    error_type: str = Field(min_length=1, max_length=256)
    message: str = Field(max_length=4096)
    returned_result_ref: EvidenceRef | None

    @model_validator(mode="after")
    def known_original_result(self) -> Self:
        if self.returned_result_ref is not None and (
            self.returned_result_ref.visibility != "public"
            or self.returned_result_ref.content_schema
            not in ("observation-read-result/1", "observation-read-result/2")
        ):
            raise ValueError("Known original public reading result required")
        return self
