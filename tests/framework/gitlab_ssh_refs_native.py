"""Same native Git collector with tiny repositories only; no database or Actor."""

import json
import os
from pathlib import Path
import pytest
from lab_generate_skill.sites.gitlab.ssh_refs_capture import REFS_CAPTURE
from lab_generate_skill.sites.gitlab.service_commands import RUBY
from lab_generate_skill.adapters.processes.capture import (
    CommandFailure,
    retained_capture,
)
from gitlab_ssh_native_fixture import TinyNative
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_complete_original_refs_without_database(node_path: Path) -> None:
    fixture = TinyNative(node_path)
    fixture.initialize_repositories(guard(30))
    try:
        raw = fixture.command(
            (
                RUBY,
                "-e",
                "require 'json';require 'open3'\n"
                + REFS_CAPTURE
                + "\nputs JSON.generate(LabGitlabSsh.refs)\n",
            ),
            guard(30),
        )
    except CommandFailure as error:
        capture = retained_capture(error)
        assert capture is not None
        (
            Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
            / "gitlab-refs-diagnostic-stderr.bin"
        ).write_bytes(capture.stderr)
        raise
    value = json.loads(raw)
    assert value["complete"] is True and len(value["repositories"]) == 3
    assert sum(row["head"] is None for row in value["repositories"].values()) == 2


@pytest.mark.parametrize(
    "damage", ["bad_head", "broken_ref", "symlink", "unknown_cache", "repository_file"]
)
def test_native_refs_keep_errors_and_foreign_entries_rejected(
    node_path: Path, damage: str
) -> None:
    fixture = TinyNative(node_path)
    fixture.initialize_repositories(guard(30))
    root = node_path / "data/git-data/repositories"
    project = root / "@hashed/ab/cd/project.git"
    if damage == "bad_head":
        (project / "HEAD").write_text("not a valid native HEAD\n")
    elif damage == "broken_ref":
        (project / "refs/heads/broken").write_text("0" * 40 + "\n")
    elif damage == "symlink":
        (root / "aliased.git").symlink_to(project)
    elif damage == "unknown_cache":
        (root / "+gitaly/state/unknown.git").mkdir()
    else:
        (root / "not-a-directory.git").write_text("not a repository")
    with pytest.raises(CommandFailure) as caught:
        fixture.command(
            (
                RUBY,
                "-e",
                "require 'json';require 'open3'\n"
                + REFS_CAPTURE
                + "\nputs JSON.generate(LabGitlabSsh.refs)\n",
            ),
            guard(30),
        )
    assert caught.value.capture.returncode != 0
    assert caught.value.capture.stderr
    assert caught.value.capture.stdout == b""
    assert (
        caught.value.capture.termination is not None
        and caught.value.capture.termination.state == "reaped"
    )
