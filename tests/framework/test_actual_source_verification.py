"""Actual driver verifies its own frozen candidate, preserving canonical defaults."""

from pathlib import Path
import hashlib
import json
from typing import Any
import pytest
import generator_engine_live as target


@pytest.mark.parametrize(
    "fault", ["none", "changed", "failed", "unstable", "relative", "wrong-type", "link"]
)
def test_explicit_candidate_and_canonical_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    canonical, candidate = tmp_path / "canonical", tmp_path / "candidate"
    canonical.mkdir()
    candidate.mkdir()
    (canonical / "source.py").write_bytes(b"canonical")
    (candidate / "source.py").write_bytes(b"candidate")
    receipt = tmp_path / "receipt.json"
    value = dict(
        passed=True,
        source_stable_during_checks=True,
        files={"source.py": hashlib.sha256(b"candidate").hexdigest()},
    )
    root: Any = candidate
    if fault == "changed":
        (candidate / "source.py").write_bytes(b"changed")
    elif fault == "failed":
        value["passed"] = False
    elif fault == "unstable":
        value["source_stable_during_checks"] = False
    elif fault == "relative":
        root = Path("candidate")
    elif fault == "wrong-type":
        root = str(candidate)
    elif fault == "link":
        root = tmp_path / "link"
        root.symlink_to(candidate, target_is_directory=True)
    receipt.write_text(json.dumps(value))
    monkeypatch.setattr(target, "P", canonical)
    with pytest.raises(ValueError):
        target.verify_source(receipt)  # Canonical bytes cannot certify candidate.
    if fault == "none":
        target.verify_source(receipt, source_root=root)
        target.verify_source(receipt, source_root=root)
    else:
        with pytest.raises((ValueError, TypeError)):
            target.verify_source(receipt, source_root=root)
