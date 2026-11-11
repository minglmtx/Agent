"""Keep a failed native startup response until its original storage retains it."""

import base64
import hashlib

from lab_generate_skill.domain.map_startup import MapStartupHttpResponse
from lab_generate_skill.domain.release import ReleaseFile


class MapHttpStartupFailure(ValueError):
    def __init__(self, port: int, path: str, status: int, body: bytes) -> None:
        if type(body) is not bytes:
            raise TypeError("Original complete startup HTTP bytes required")
        self.response = MapStartupHttpResponse(
            port=port,
            path=path,
            status=status,
            body_base64=base64.b64encode(body).decode(),
            body_sha256=hashlib.sha256(body).hexdigest(),
            body_size_bytes=len(body),
        )
        self.reason_code = "MAP_STARTUP_HTTP_NON_200"
        self.record: ReleaseFile | None = None
        super().__init__(
            "Original native HTTP readiness request did not complete with 200"
        )

    def recorded(self, entry: ReleaseFile) -> None:
        entry = ReleaseFile.model_validate(entry)
        if (
            self.record is not None
            or entry.path != "startup-http-failure.json"
            or entry.executable
        ):
            raise ValueError("One exact original startup failure record required")
        self.record = entry
        # The existing bounded RemoteError carries this exact durable-file hash.
        self.reason_code = "MAP_STARTUP_HTTP_RECORD_" + entry.sha256
