"""Original durable acquisition is consumed, never reconstructed or initialized."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.sites.storage_original import (
    OriginalSiteAcquisitionReader,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    EvidenceNotFound,
)
from site_storage_fixtures import private_configuration
from site_resource_fixtures import resource_case
from test_site_resource import enter
from test_slurm_commands import guard


def test_original_reader_checks_persisted_resource_intent_config_and_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = resource_case(tmp_path, monkeypatch, config=private_configuration(tmp_path))
    reader = OriginalSiteAcquisitionReader()
    with enter(c) as registered:
        original = reader.read(c.spec.configuration, guard())
        assert original.record.state == "acquired" and original.spec == c.spec
        assert original.acquired.details.ready == registered.site.ready
        assert original.acquired.details.site_started is False
        before = c.journal.read(c.spec.token, c.op)
        assert reader.read(c.spec.configuration, guard()) == original
        assert c.journal.read(c.spec.token, c.op) == before
    assert reader.read(c.spec.configuration, guard()).record.state == "closed"


@pytest.mark.parametrize(
    "damage",
    ["missing_journal", "changed_config", "corrupt_acquired", "missing_intent"],
)
def test_missing_foreign_or_corrupt_ownership_is_not_a_new_namespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    c = resource_case(tmp_path, monkeypatch, config=private_configuration(tmp_path))
    reader = OriginalSiteAcquisitionReader()
    with enter(c):
        original = reader.read(c.spec.configuration, guard())
        value = c.spec.configuration
        if damage == "missing_journal":
            plan = value.private_evidence
            assert plan is not None
            value = value.model_copy(
                update={
                    "private_evidence": plan.model_copy(
                        update={"resource_journal_root": str(tmp_path / "unregistered")}
                    )
                }
            )
        elif damage == "changed_config":
            value = value.model_copy(
                update={
                    "files": value.files.model_copy(
                        update={"source_path": str(tmp_path / "foreign" / "gitlab.sif")}
                    )
                }
            )
        else:
            ref = (
                original.record.events[2].evidence[0]
                if damage == "corrupt_acquired"
                else original.record.events[1].evidence[0]
            )
            path = tmp_path / "evidence/blobs" / ref.sha256
            if damage == "corrupt_acquired":
                path.write_bytes(b"corrupted")
            else:
                path.unlink()
        with pytest.raises(
            (
                OwnershipConflict,
                EvidenceIntegrityError,
                EvidenceNotFound,
                FileNotFoundError,
            )
        ):
            reader.read(value, guard())
        assert not (tmp_path / "unregistered").exists()
