"""Preflight the new no-Actor live entry's original private storage declarations."""

from pathlib import Path
import pytest
from site_resource_fixtures import resource_case
from reddit_initialization_fixture import source_hooks
from storage_installation_fixtures import storage_installation
from reddit_site_native_plan import native_configuration


def test_no_actor_source_uses_same_original_storage_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installation = storage_installation()
    hooks = source_hooks(tmp_path, installation, "12345")
    assert hooks.private_site_plan is not None
    config = native_configuration(
        installation,
        job_id="12345",
        parent=Path("/tmp/lab-reddit-declaration"),
        private_evidence=hooks.private_site_plan,
    )
    assert config.token.owner == hooks.owner
    assert config.private_evidence is not None
    assert config.private_evidence.config.evidence_root == str(
        tmp_path / "source-evidence"
    )
    assert config.private_evidence.resource_journal_root == str(tmp_path / "journal")
    assert config.site_id == "reddit"
    assert config.files.node_root == "/tmp/lab-reddit-declaration/instance"

    assembled = resource_case(
        tmp_path, monkeypatch, config=config, store=hooks.evidence
    )
    assert assembled.evidence is hooks.evidence
    assert assembled.spec.configuration.private_evidence == hooks.private_site_plan
    assert assembled.spec.token.owner == hooks.owner
    assert not assembled.channels
