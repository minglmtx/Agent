"""Full passive page facts bound to an existing unique browser return.

No task judgment, new Observation, browser action or source-admission claim.
Failed reads/writes are quarantined and are never automatically repeated.
"""

import hashlib
import json
import os
import threading
import traceback
from typing import Any, Literal
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
)
from lab_generate_skill.domain.map_private_artifact import (
    MapPrivateArtifactPlan,
    MapArtifactPlan,
)
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_private_artifact import MapArtifactSink
from .native_surface_script import COMBINED_READ


class NativeSurfaceCapture:
    def __init__(
        self,
        plan: MapArtifactPlan,
        sink: MapArtifactSink,
        evidence_control: OperationControl,
    ) -> None:
        self.plan = MapPrivateArtifactPlan.model_validate(plan)
        if self.plan.producer != "browser_process":
            raise ValueError("Original browser process artifact plan required")
        self.sink, self.evidence_control = sink, evidence_control
        self.owner = os.getpid(), threading.get_ident()
        self.page: Any = None
        self.last_readout: BrowserReadout | None = None
        self.unique_count = 0
        self.terminal_attempted = False
        self.errors: list[BaseException] = []
        self.pending_record: dict[str, Any] | None = None
        self.records: list[ReleaseFile] = []
        self.close_attempted = False
        self.cleanup_errors: list[BaseException] = []
        self.last_map_visible = False

    def require_owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original browser thread owns Map surface reads")

    def healthy(self) -> None:
        self.require_owner()
        if self.close_attempted:
            raise InvalidTransition("Original Map surface collector is closed")
        if self.errors:
            raise EvidenceIntegrityError("Original Map surface capture failed")

    def bind(self, page: Any) -> None:
        self.healthy()
        if self.page is not None or page is None:
            raise InvalidTransition("Original surface page binds exactly once")
        self.page = page

    def capture(
        self,
        page: Any,
        readout: BrowserReadout,
        control: OperationControl,
        *,
        phase: Literal["unique_return", "terminal"],
    ) -> ReleaseFile:
        self.healthy()
        try:
            if phase not in ("unique_return", "terminal"):
                raise ValueError("Explicit original surface capture phase required")
            if not isinstance(readout, BrowserReadout):
                raise TypeError("Original unique browser readout required")
            BrowserReadout.model_validate(readout)
            if (
                self.page is None
                or page is not self.page
                or readout.scope != self.plan.scope
            ):
                raise OwnershipConflict("Original page and readout scope required")
            if self.terminal_attempted:
                raise InvalidTransition("Original final surface already attempted")
            if phase == "unique_return":
                if readout.observation.sequence != self.unique_count:
                    raise InvalidTransition(
                        "Original continuous unique return required"
                    )
                self.unique_count += 1
                self.last_readout = readout
            else:
                if readout is not self.last_readout:
                    raise OwnershipConflict(
                        "Terminal facts must bind the original last return"
                    )
                self.terminal_attempted = True
            control.checkpoint()
            raw = page.evaluate(COMBINED_READ)
            self.pending_record = dict(
                schema_version="map-original-native-page-facts/1",
                plan_sha256=self.plan.digest,
                phase=phase,
                unique_observation_sequence=readout.observation.sequence,
                original_readout=readout.model_dump(mode="json"),
                timing_semantics="single_passive_page_evaluation_after_unique_return_not_atomic_with_return",
                new_action_or_observation=False,
                semantic_success_or_admission_claim=False,
                facts=raw,
            )
            data = json.dumps(
                self.pending_record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
            name = f"map-page-{readout.observation.sequence}-{phase}.json"
            expected = ReleaseFile(
                path=name,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
                executable=False,
            )
            actual = self.sink.retain(name, data, self.evidence_control)
            if actual != expected:
                raise EvidenceIntegrityError("Original complete page facts pin differs")
            self.records.append(actual)
            # Preserve even an invalid returned value before refusing it. Full
            # semantic field/type checks belong to the selected final evaluator.
            if (
                type(raw) is not dict
                or set(raw) != {"surface", "route"}
                or type(raw["surface"]) is not dict
                or type(raw["route"]) is not dict
            ):
                raise ValueError("Original surface/route reader envelope differs")
            self.last_map_visible = raw["surface"].get("map_visible") is True
            control.checkpoint()
            self.pending_record = None
            return actual
        except BaseException as error:
            self.errors.append(error)
            raise

    def close(self, control: OperationControl) -> None:
        """Persist original capture failures once; never retry an unknown write."""
        self.require_owner()
        if not self.close_attempted:
            self.close_attempted = True
            try:
                data = json.dumps(
                    dict(
                        schema_version="map-original-native-page-close/1",
                        plan_sha256=self.plan.digest,
                        unique_return_count=self.unique_count,
                        terminal_attempted=self.terminal_attempted,
                        complete_records=[
                            r.model_dump(mode="json") for r in self.records
                        ],
                        pending_record_retained=self.pending_record is not None,
                        errors=[
                            "".join(traceback.format_exception(e)) for e in self.errors
                        ],
                        task_success_or_admission_claim=False,
                    ),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
                expected = ReleaseFile(
                    path="map-page-close.json",
                    size_bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    executable=False,
                )
                actual = self.sink.retain(expected.path, data, control)
                if actual != expected:
                    raise EvidenceIntegrityError(
                        "Original page close record pin differs"
                    )
            except BaseException as error:
                self.cleanup_errors.append(error)
        if self.cleanup_errors:
            raise BaseExceptionGroup(
                "Original page capture close errors", self.cleanup_errors
            )
