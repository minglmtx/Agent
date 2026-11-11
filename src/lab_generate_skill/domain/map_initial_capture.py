"""Private original initialization facts bound to the unique first return."""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract, Sha256
from .map_private_artifact import MapPrivateArtifactPlan
from .release import ReleaseFile
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class MapInitialCapture(Contract):
    schema_version: Literal["map-initial-capture/1"] = "map-initial-capture/1"
    plan: MapPrivateArtifactPlan
    collection_sha256: Sha256
    readout_sha256: Sha256
    observation_sha256: Sha256
    readiness_file: ReleaseFile
    readiness_json: str = Field(min_length=2, max_length=196608)

    @model_validator(mode="after")
    def original(self) -> Self:
        raw = self.readiness_json.encode()
        if (
            self.plan.producer != "browser_process"
            or self.readiness_file.path != "map-initial-readiness.json"
            or (
                self.readiness_file.executable
                or len(raw) > 196608
                or (len(raw), hashlib.sha256(raw).hexdigest())
                != (self.readiness_file.size_bytes, self.readiness_file.sha256)
            )
        ):
            raise ValueError("Original complete bounded Map readiness file required")
        return self


class MapInitialEvidence(Contract):
    schema_version: Literal["map-initial-evidence/1"] = "map-initial-evidence/1"
    intent_ref: EvidenceRef
    result_ref: EvidenceRef

    @model_validator(mode="after")
    def originals(self) -> Self:
        for ref, schema in (
            (self.intent_ref, "browser-capture-intent/1"),
            (self.result_ref, "browser-capture-result/1"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json":
                raise ValueError(
                    "Original private Map capture JSON references required"
                )
        return self
