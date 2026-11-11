"""Opaque binary >64MiB and new-interpreter full-file replay, no model calls."""

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from lab_generate_skill.domain.training_output import SFTCheckpoint
from training_entry_fixtures import training_case, TrainingCase
from training_output_fixtures import output_case


def test_complete_larger_than_small_object_limit_preserves_tail_and_only_small_references(
    training_case: TrainingCase,
) -> None:
    c = output_case(training_case, "larger-than-CAS", large_bytes=65 * 1024**2)
    returned = c.returned()
    ref = c.checkpoints().publish(c.plan, c.data, c.closure, returned, c.control())
    snapshot = c.checkpoints().read(ref, c.data, c.control())
    name = "checkpoint-000001/training_state.pt"
    original = next(f for f in snapshot.source.files if f.path == name)
    assert original.size_bytes == 65 * 1024**2 + len(b"unit-original-tail")
    assert original.size_bytes > 64 * 1024**2 and max(c.store.put_sizes) < 8 * 1024**2
    file = Path(snapshot.artifact.root) / name
    assert file.stat().st_size == original.size_bytes
    with file.open("rb") as stream:
        stream.seek(-len(b"unit-original-tail"), 2)
        assert stream.read() == b"unit-original-tail"
    assert ref.size_bytes < 8 * 1024**2


def test_fresh_readonly_interpreter_revalidates_native_source_closure_and_all_files(
    training_case: TrainingCase, tmp_path: Path
) -> None:
    c = output_case(training_case, "new-interpreter")
    returned = c.returned()
    reference = c.checkpoints().publish(
        c.plan, c.data, c.closure, returned, c.control()
    )
    original = c.checkpoints().read(reference, c.data, c.control())
    assert c.data.manifest is not None
    bundle = dict(
        unit_native_fixture_not_weights=True,
        workspace=str(c.workspace),
        reference=reference.model_dump(mode="json"),
        training=c.plan.training.model_dump(mode="json"),
        receipt=c.data.receipt.model_dump(mode="json"),
        manifest=c.data.manifest.model_dump(mode="json"),
        examples=[e.model_dump(mode="json") for e in c.data.examples],
    )
    input_path, result_path = tmp_path / "input.json", tmp_path / "result.json"
    input_path.write_text(json.dumps(bundle))
    writes = len(c.store.put_sizes)
    child = subprocess.run(
        [
            sys.executable,
            "-B",
            str(Path(__file__).with_name("training_output_child.py")),
            str(input_path),
            str(result_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=90,
    )
    (tmp_path / "full-child-stdout.txt").write_text(child.stdout)
    (tmp_path / "full-child-stderr.txt").write_text(child.stderr)
    assert child.returncode == 0, child.stdout + child.stderr
    assert json.loads(child.stdout)["pid"] != os.getpid()
    parsed = SFTCheckpoint.model_validate_json(result_path.read_bytes())
    assert parsed == original and len(c.store.put_sizes) == writes
