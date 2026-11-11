"""Actual Shopping original checkpoint location, never an empty fallback or grant."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.source_construction_inputs import (
    source_construction_inputs,
)
from test_shopping_category_navigation_input import originals as originals
from test_slurm_commands import guard

CHECKPOINT = ("integration_20261103", "next_compatible_group", "evidence_checkpoints")


def test_actual_shopping_location_reads_selected_original_index_and_missing_is_not_empty(
    tmp_path: Path,
    originals: Any,
) -> None:
    task = originals[0][2].identity
    assert task.site == "shopping"
    path = tmp_path / "original-plan.json"
    path.write_text(
        json.dumps(
            {
                "integration_20261103": {
                    "next_compatible_group": {"evidence_checkpoints": {"members": {}}}
                }
            }
        )
    )
    before = path.read_bytes()
    needs = source_construction_inputs(
        path, task, "33", guard(30), checkpoint_path=CHECKPOINT
    )
    assert (
        needs["source_task_id"] == task.source_task_id
        and not needs["runtime_or_resume_authority"]
    )
    assert len(needs["required_new_facts"]) == 4 and len(needs["reuse"]) == 2
    with pytest.raises(ValueError, match="Missing original source checkpoint"):
        source_construction_inputs(path, task, "33", guard(30))
    assert path.read_bytes() == before and list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("location", [(), [], ("",), ("missing",), ("x" * 257,)])
def test_invalid_or_absent_original_location_never_allows_reconstruction(
    tmp_path: Path,
    originals: Any,
    location: Any,
) -> None:
    path = tmp_path / "original-plan.json"
    path.write_text("{}")
    with pytest.raises(ValueError):
        source_construction_inputs(
            path, originals[0][2].identity, "33", guard(30), checkpoint_path=location
        )
    assert path.read_text() == "{}" and list(tmp_path.iterdir()) == [path]
