"""Original immutable manifest membership and complete-byte validation for terminal consumers."""

import hashlib
from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.map_browser_collection import MapBrowserPublication
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.map_published_files import MapPublishedFiles
from lab_generate_skill.ports.lifecycle import OperationControl

T = TypeVar("T", bound=Contract)


def private_bytes(
    store: EvidenceReader, ref: EvidenceRef, schema: str, control: OperationControl
) -> bytes:
    private_state_ref(ref, schema)
    if ref.media_type != "application/json":
        raise ValueError("Original Map private JSON required")
    raw = store.read(ref, control=control)
    if (len(raw), hashlib.sha256(raw).hexdigest()) != (ref.size_bytes, ref.sha256):
        raise EvidenceIntegrityError("Original Map terminal CAS bytes changed")
    control.checkpoint()
    return raw


def private_record(
    store: EvidenceReader,
    ref: EvidenceRef,
    schema: str,
    model: type[T],
    control: OperationControl,
) -> T:
    raw = private_bytes(store, ref, schema, control)
    value = model.model_validate_json(raw)
    if value.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError("Original Map terminal record is not canonical")
    return value


class TerminalFiles:
    def __init__(
        self,
        publication: MapBrowserPublication,
        files: MapPublishedFiles,
        control: OperationControl,
    ) -> None:
        self.publication, self.files = publication, files
        self.manifest = files.manifest(publication.handle, control)
        if self.manifest.plan != publication.plan:
            raise EvidenceIntegrityError("Original terminal manifest changed plan")
        self.members = {f.path: f for f in self.manifest.artifact.files}
        if (
            self.members.get(publication.terminal_readout.path)
            != publication.terminal_readout
        ):
            raise EvidenceIntegrityError(
                "Original terminal readout is not the exact manifest member"
            )

    def read(self, name: str, control: OperationControl) -> bytes:
        entry = self.members.get(name)
        if entry is None:
            raise EvidenceIntegrityError("Original terminal member missing: " + name)
        raw = self.files.read(self.publication.handle, name, control)
        if entry.executable or (len(raw), hashlib.sha256(raw).hexdigest()) != (
            entry.size_bytes,
            entry.sha256,
        ):
            raise EvidenceIntegrityError(
                "Complete original terminal member bytes changed"
            )
        control.checkpoint()
        return raw

    def pinned(self, entry: ReleaseFile, control: OperationControl) -> bytes:
        if self.members.get(entry.path) != entry:
            raise EvidenceIntegrityError(
                "Terminal response changed its original member pin"
            )
        return self.read(entry.path, control)
