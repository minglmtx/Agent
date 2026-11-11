"""Repeated engineering verification retains the original read context."""

from pathlib import Path
import pytest
from qualified_source_native import QualifiedSource
from state_qualification_fixtures import qualified
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_repeated_source_environment_verification_keeps_same_deadline(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with qualified(tmp_path, node_path, monkeypatch) as c:
        authority = object.__new__(QualifiedSource)
        authority.c = c["c"]
        authority.saved = dict(
            environment_selection=c["environment"],
            environment_selection_ref=c["selection_ref"],
            snapshot_ref=c["environment"].snapshot_ref,
            snapshot=c["snapshot"],
        )
        for _ in range(2):
            authority.verify(
                c["environment"].scope,
                c["selection_ref"],
                "environment",
                c["operation"],
                guard(),
            )
