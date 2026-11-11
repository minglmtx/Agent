"""Current native batch callback -> complete private files, without network effects.

Caller supplies the original bounded evidence control (including failure
retention), not a renewed HTTP read deadline. Each transition gets a new name;
known cap/body repeats in the ledger are observations, never new HTTP attempts.
"""

import hashlib
import json
import re
from typing import Any
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.errors import InvalidTransition, EvidenceIntegrityError
from lab_generate_skill.ports.map_private_artifact import MapArtifactSink
from lab_generate_skill.ports.lifecycle import OperationControl


class NativeBatchRetention:
    def __init__(
        self, batch_id: str, sink: MapArtifactSink, control: OperationControl
    ) -> None:
        if (
            not isinstance(batch_id, str)
            or re.fullmatch(r"[a-z][a-z0-9-]{0,31}", batch_id) is None
            or not callable(getattr(sink, "retain", None))
        ):
            raise ValueError(
                "Explicit bounded batch identity and private sink required"
            )
        self.batch_id, self.sink, self.control = batch_id, sink, control
        self.sequence = 0
        self.failed = False
        self.last_body: ReleaseFile | None = None
        self.last_event: ReleaseFile | None = None
        self.pending_record: bytes | None = None

    def __call__(self, index: int, row: dict[str, Any], payload: bytes | None) -> None:
        if self.failed:
            raise InvalidTransition("Failed native event retention cannot be replayed")
        if (
            type(index) is not int
            or not 0 <= index < 255
            or not isinstance(row, dict)
            or type(row.get("request_index")) is not int
            or row["request_index"] != index
            or (payload is not None and not isinstance(payload, bytes))
        ):
            raise ValueError(
                "Original bounded native request index and byte record required"
            )
        if self.sequence >= 2048:
            raise ValueError("Native batch transition budget exhausted")
        self.control.checkpoint()
        name = f"{self.batch_id}-event-{self.sequence:04d}"
        expected = None
        if payload is not None:
            if len(payload) > 64 * 1024 * 1024:
                raise ValueError("Native child body exceeds original byte budget")
            expected = ReleaseFile(
                path=name + ".bin",
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
                executable=False,
            )
            if (
                type(row.get("bytes")) is not int
                or row["bytes"] != len(payload)
                or row.get("sha256") != expected.sha256
                or type(row.get("body_complete")) is not bool
            ):
                raise EvidenceIntegrityError(
                    "Native retained body differs from original response metadata"
                )
        data = json.dumps(
            dict(
                schema_version="map-native-transport-event/1",
                batch_id=self.batch_id,
                event_index=self.sequence,
                request_index=index,
                source_record=row,
                body=expected.model_dump(mode="json") if expected is not None else None,
            ),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        if len(data) > 1024 * 1024:
            raise ValueError("Bounded native metadata event required")
        self.pending_record = data
        self.last_body = None
        self.last_event = None
        self.sequence += 1
        try:
            if expected is not None:
                assert payload is not None
                self.last_body = self.sink.retain(expected.path, payload, self.control)
                if self.last_body != expected:
                    raise EvidenceIntegrityError(
                        "Private sink returned different original body pin"
                    )
            self.last_event = self.sink.retain(name + ".json", data, self.control)
            if (
                self.last_event.path != name + ".json"
                or self.last_event.size_bytes != len(data)
                or self.last_event.sha256 != hashlib.sha256(data).hexdigest()
                or self.last_event.executable
            ):
                raise EvidenceIntegrityError(
                    "Private sink returned different native event pin"
                )
            self.pending_record = None
        except BaseException:
            self.failed = True
            raise
