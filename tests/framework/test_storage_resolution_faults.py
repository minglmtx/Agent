"""A physical observation cannot replace mandatory authority or commit checks."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage.observed_inspection import (
    ObservedStorageInspection,
)
from lab_generate_skill.adapters.storage.worker_protocol import decode_command
from lab_generate_skill.adapters.storage.session_resolution import (
    resolve_registered_storage,
)
from lab_generate_skill.adapters.storage.resolution_result import (
    StorageResolutionFailure,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from evidence_session_fixtures import binding, resolution
from evidence_session_storage_fixtures import snapshot_path
from registered_exchange_fixtures import harness


@pytest.mark.parametrize("fault", ["authority", "wrong_ack"])
def test_resolution_cannot_bypass_authority_or_trust_wrong_ack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    f = harness(tmp_path)
    original = f.execute()
    proposed = resolution(original.intent)
    before = snapshot_path(tmp_path / "sessions").read_bytes()
    if fault == "authority":

        def deny(*args: object, **kwargs: object) -> None:
            raise OwnershipConflict("unverified real worker")

        monkeypatch.setattr(f.ledger._authority, "verify_resolution", deny)
    else:
        monkeypatch.setattr(f.ledger, "resolve", lambda *args: original.snapshot)
    with pytest.raises(StorageResolutionFailure) as caught:
        resolve_registered_storage(
            f.raw,
            binding(),
            f.ledger,
            proposed.operation,
            f.controls,
            proposed.worker_end,
            ObservedStorageInspection(decode_command(f.raw)[0]),
        )
    assert caught.value.result.snapshot is None
    assert snapshot_path(tmp_path / "sessions").read_bytes() == before
