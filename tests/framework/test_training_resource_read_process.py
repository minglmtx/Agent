"""Fresh resource proof consumer, no new native/model/Slurm requests."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from lab_generate_skill.domain.training_output import SFTCheckpoint
from test_training_resource import train as train_unit_original
from test_slurm_commands import guard
from training_resource_fixtures import unit_case


def _files(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_fresh_readonly_process_reconstructs_original_resource_wire_and_full_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = unit_case(tmp_path / "original-unit-resource", monkeypatch)
    result, runtime = train_unit_original(c)
    original = runtime.checkpoints.read(result.checkpoint_ref, c.c.source.data, guard())
    workspace = Path(c.spec.configuration.evidence_root).parent
    descriptor = dict(
        unit_model_kernel_and_source_not_real_training=True,
        spec=c.spec.model_dump(mode="json"),
        reference=result.checkpoint_ref.model_dump(mode="json"),
        workspace=str(workspace),
    )
    input_path, result_path = tmp_path / "input.json", tmp_path / "result.json"
    input_path.write_text(json.dumps(descriptor))
    before = _files(workspace)
    sent = tuple(c.channels[0].sent)
    cores = len(c.cores)
    child = subprocess.run(
        [
            sys.executable,
            "-B",
            str(Path(__file__).with_name("training_resource_read_child.py")),
            str(input_path),
            str(result_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=90,
    )
    (tmp_path / "full-read-child-stdout.txt").write_text(child.stdout)
    (tmp_path / "full-read-child-stderr.txt").write_text(child.stderr)
    assert child.returncode == 0, child.stdout + child.stderr
    facts = json.loads(child.stdout)
    assert facts["pid"] != os.getpid() and facts["put_attempts"] == 0
    # The original Store checks source/closure before and after reading all files.
    assert facts["closure"] == "closed" and facts["authority_phases"] == [
        "read",
        "read",
    ]
    parsed = SFTCheckpoint.model_validate_json(result_path.read_bytes())
    assert parsed == original and facts["complete_files"] == len(original.source.files)
    assert facts["complete_bytes"] == sum(f.size_bytes for f in original.source.files)
    assert _files(workspace) == before
    assert tuple(c.channels[0].sent) == sent and len(c.cores) == cores == 1
