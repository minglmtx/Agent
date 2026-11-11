"""Fresh interpreter reads original sealed evidence after native resources close."""

import os
import json
import subprocess
import sys
from pathlib import Path
import pytest
from lab_generate_skill.domain.review import ReviewReceipt
from construction_review_fixtures import construction_review_case
from construction_review_recorded_fixtures import recorded_bundle


def test_fresh_process_reconstructs_original_read_dependencies_without_runner_or_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = construction_review_case(tmp_path / "case", monkeypatch)
    bundle = recorded_bundle(c, c.plan("separate-process"))
    input_path, output_path = tmp_path / "input.json", tmp_path / "review.json"
    input_path.write_text(bundle.model_dump_json())
    # Original native/model and Teacher are closed/known facts before the new
    # interpreter imports current framework code. Only metadata goes across.
    run = subprocess.run(
        [
            sys.executable,
            "-B",
            str(Path(__file__).with_name("construction_review_child.py")),
            str(input_path),
            str(output_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=90,
    )
    (tmp_path / "complete-child-stdout.txt").write_text(run.stdout)
    (tmp_path / "complete-child-stderr.txt").write_text(run.stderr)
    assert run.returncode == 0, run.stdout + run.stderr
    metadata = json.loads(run.stdout)
    assert metadata["pid"] != os.getpid()
    result = ReviewReceipt.model_validate_json(output_path.read_bytes())
    assert result.status == "verified" and result.training_admission == "not_evaluated"
    assert result.selected_skill_ref == c.fifth.task.plan.skill_ref
    assert len(result.findings) == 5
    assert (
        c.control.source.native.loader.session.calls == 5
        and len(c.control.wire.transport.calls) == 1
    )
    assert (
        c.control.source.data.journal().read(c.plan("after-child").operation)
        == c.sealed
    )
