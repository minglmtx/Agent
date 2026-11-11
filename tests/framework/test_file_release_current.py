"""Real stable pointer storage, denied admissions, loss and read-only status."""

from pathlib import Path
from collections.abc import Callable
import pytest
from lab_generate_skill.adapters.releases.current import FileReleaseCurrent
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    RevisionConflict,
    OperationStopped,
)
from lab_generate_skill.domain.release_activation import ReleaseSwitch
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.ports.release_current import ReleaseCurrent
from release_current_fixtures import store, op, switch, disk, UnitCurrentAuthority


def test_persist_reopen_two_switches_and_old_replay(tmp_path: Path) -> None:
    authority = UnitCurrentAuthority()
    ledger: ReleaseCurrent = store(tmp_path, authority)
    empty = ledger.initialize(op())
    assert empty.active is None
    first, second = switch(), switch(1, "two")
    one = ledger.activate(first)
    two = ledger.activate(second)
    assert one.revision == 1 and two.revision == 2
    before = disk(tmp_path)
    assert ledger.activate(first) == two
    assert authority.switches == 2
    assert store(tmp_path).read(op("read")) == two
    assert store(tmp_path).initialize(op("repeat-init")) == two
    assert disk(tmp_path) == before
    authority.deny_switch = True
    assert ledger.activate(first) == two  # History confirmation, not reactivation.
    with pytest.raises(OwnershipConflict):
        ledger.activate(switch(2, "three"))
    assert disk(tmp_path) == before


def test_missing_read_or_update_creates_nothing(tmp_path: Path) -> None:
    with pytest.raises(EvidenceIntegrityError):
        store(tmp_path).read(op())
    with pytest.raises(EvidenceIntegrityError):
        store(tmp_path).activate(switch())
    assert disk(tmp_path) == {}


def test_access_denial_and_expiration_have_no_effect(tmp_path: Path) -> None:
    from datetime import timedelta

    auth = UnitCurrentAuthority()
    auth.deny_access = True
    with pytest.raises(OwnershipConflict):
        store(tmp_path, auth).initialize(op())
    past = op().model_copy(update={"deadline": op().deadline - timedelta(seconds=120)})
    with pytest.raises(OperationStopped):
        store(tmp_path).initialize(past)
    assert disk(tmp_path) == {}


def test_switch_denied_or_stale_leaves_original_bytes(tmp_path: Path) -> None:
    auth = UnitCurrentAuthority()
    ledger = store(tmp_path, auth)
    ledger.initialize(op())
    before = disk(tmp_path)
    auth.deny_switch = True
    first = switch()
    with pytest.raises(OwnershipConflict):
        ledger.activate(first)
    assert disk(tmp_path) == before
    auth.deny_switch = False
    ledger.activate(first)
    before = disk(tmp_path)
    with pytest.raises(RevisionConflict):
        ledger.activate(switch(0, "two"))
    assert disk(tmp_path) == before and auth.switches == 1


@pytest.mark.parametrize(
    "damage",
    ["snapshot", "marker", "both", "birth", "lock", "malformed", "duplicate", "link"],
)
def test_used_pointer_never_reinitialized_or_repaired(
    tmp_path: Path, damage: str
) -> None:
    ledger = store(tmp_path)
    ledger.initialize(op())
    ledger.activate(switch())
    path = tmp_path / "system-current.json"
    if damage in ("snapshot", "both"):
        path.unlink()
    if damage in ("marker", "both"):
        Path(str(path) + ".initialized").unlink()
    if damage == "birth":
        Path(str(path) + ".pending-" + "0" * 64).unlink()
    if damage == "lock":
        Path(str(path) + ".lock").unlink()
    if damage == "malformed":
        path.write_bytes(b"[]")
    if damage == "duplicate":
        path.write_bytes(b'{"switches":[],"switches":[]}')
    if damage == "link":
        original = path.read_bytes()
        path.unlink()
        (tmp_path / "foreign").write_bytes(original)
        path.symlink_to(tmp_path / "foreign")
    before = disk(tmp_path)
    calls: tuple[Callable[[], ReleaseCurrentSnapshot], ...] = (
        lambda: ledger.initialize(op("again")),
        lambda: ledger.read(op("read")),
        lambda: ledger.activate(switch(1, "two")),
    )
    for call in calls:
        with pytest.raises(
            (EvidenceIntegrityError, EvidenceNotFound, OwnershipConflict)
        ):
            call()
    assert disk(tmp_path) == before


def test_capacity_is_immutable_and_full_history_remains_readable(
    tmp_path: Path,
) -> None:
    from lab_generate_skill.domain.errors import JournalCapacityExceeded

    ledger = store(tmp_path, limit=1)
    ledger.initialize(op())
    first = switch()
    saved = ledger.activate(first)
    before = disk(tmp_path)
    with pytest.raises(JournalCapacityExceeded):
        ledger.activate(switch(1, "two"))
    with pytest.raises(OwnershipConflict):
        store(tmp_path, limit=2).initialize(op("larger"))
    assert ledger.read(op("read")) == saved and ledger.activate(first) == saved
    assert disk(tmp_path) == before


def test_authority_failure_chain_is_preserved(tmp_path: Path) -> None:
    class Failing(UnitCurrentAuthority):
        def authorize_switch(
            self, prior: ReleaseCurrentSnapshot, change: ReleaseSwitch, control: object
        ) -> None:
            raise ExceptionGroup(
                "verification and cleanup", [OSError("first"), OSError("close")]
            )

    ledger = store(tmp_path, Failing())
    ledger.initialize(op())
    before = disk(tmp_path)
    with pytest.raises(ExceptionGroup) as caught:
        ledger.activate(switch())
    assert [str(e) for e in caught.value.exceptions] == ["first", "close"]
    assert not hasattr(caught.value, "release_current_candidate")
    assert disk(tmp_path) == before


def test_canonical_root_required(tmp_path: Path) -> None:
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(EvidenceIntegrityError):
        store(alias).initialize(op())
    assert sorted(x.name for x in tmp_path.iterdir()) == ["alias"]
