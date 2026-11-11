"""Complete closed-instance diagnostics, no service requests or historical mutation."""

import hashlib
from pathlib import Path
import pytest
from lab_generate_skill.ports.lifecycle import OperationControl
from map_startup_log_preservation import preserve_closed_startup_logs
from test_slurm_commands import guard


def source(parent: Path, service: str, body: bytes) -> Path:
    path = parent / "instance/logs/generation-1" / f"{service}-1" / f"{service}.log"
    path.parent.mkdir(parents=True)
    path.write_bytes(body)
    return path


def test_complete_large_and_empty_logs_missing_services_and_duplicate_refusal(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    body = b"original-private-renderer-line\n" * 40000
    original = source(parent, "renderd", body)
    source(parent, "tile_http", b"")
    output = tmp_path / "saved"
    result = preserve_closed_startup_logs(parent, output, guard())
    assert result["present_logs_saved_completely"] and len(result["logs"]) == 2
    rows = {r["service"]: r for r in result["logs"]}
    assert rows["renderd"]["sha256"] == hashlib.sha256(body).hexdigest()
    assert (
        rows["renderd"]["bytes"] == len(body)
        and (output / "renderd.log").read_bytes() == body
    )
    assert rows["tile_http"]["bytes"] == 0 and original.read_bytes() == body
    assert "rails_server" in result["absent_services"]
    with pytest.raises(FileExistsError):
        preserve_closed_startup_logs(parent, output, guard())
    assert original.read_bytes() == body


@pytest.mark.parametrize("kind", ["parent-symlink", "file-symlink", "directory"])
def test_foreign_symbolic_or_nonfile_log_refused_before_destination(
    tmp_path: Path, kind: str
) -> None:
    parent = tmp_path / "private"
    parent.mkdir()
    original = source(parent, "renderd", b"original")
    selected = parent
    if kind == "parent-symlink":
        selected = tmp_path / "alias"
        selected.symlink_to(parent, target_is_directory=True)
    elif kind == "file-symlink":
        original.unlink()
        outside = tmp_path / "outside"
        outside.write_bytes(b"foreign")
        original.symlink_to(outside)
    else:
        original.unlink()
        original.mkdir()
    output = tmp_path / "saved"
    with pytest.raises(ValueError):
        preserve_closed_startup_logs(selected, output, guard())
    assert not output.exists()


@pytest.mark.parametrize("after", [False, True])
def test_cancel_before_or_during_copy_keeps_original_and_partial_diagnostics(
    tmp_path: Path, after: bool
) -> None:
    parent = tmp_path / "private"
    parent.mkdir()
    body = b"original" * 200000
    original = source(parent, "renderd", body)
    output = tmp_path / "saved"

    class Cancel:
        calls = 0

        def checkpoint(self) -> float:
            self.calls += 1
            if not after or self.calls == 5:
                raise TimeoutError("original diagnostic cancellation")
            return 20.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    control: OperationControl = Cancel()
    with pytest.raises(TimeoutError):
        preserve_closed_startup_logs(parent, output, control)
    assert original.read_bytes() == body
    assert output.exists() is after
    if after:
        assert 0 < (output / "renderd.log").stat().st_size < len(body)
