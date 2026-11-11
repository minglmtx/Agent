"""Candidate-to-current integration using explicit unit acceptance, not deployment."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.release_activation import (
    ReleaseActivation,
    ReleaseSwitch,
)
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from release_candidate_fixtures import setup, writable
from release_current_fixtures import store, op, UnitCurrentAuthority, ref
from test_slurm_commands import guard


def test_candidate_pins_are_checked_by_authority_before_actual_pointer_switch(
    tmp_path: Path,
) -> None:
    try:
        case = setup(tmp_path)
        m = case.metadata
        candidate = case.candidates.stage(m.release, m.reference, m.supported, guard())
        proof = case.store.put(
            b"unit acceptance only",
            EvidenceMetadata(
                media_type="application/json",
                content_schema="release-acceptance/1",
                visibility="private",
                producer="unit-acceptance",
            ),
        )

        class VerifiedUnitAuthority(UnitCurrentAuthority):
            def authorize_switch(
                self,
                prior: ReleaseCurrentSnapshot,
                change: ReleaseSwitch,
                control: OperationControl,
            ) -> None:
                a = change.activation
                if (a.manifest_ref, a.registry_ref, a.acceptance_ref, a.release_id) != (
                    candidate.manifest_ref,
                    candidate.registry_ref,
                    proof,
                    m.release.release_id,
                ):
                    raise OwnershipConflict("unit approval is for another candidate")
                assert case.store.read(proof) == b"unit acceptance only"
                loaded = case.documents.manifest(a.manifest_ref, control)
                assert loaded == m.release
                case.files.verify(loaded, control)
                super().authorize_switch(prior, change, control)

        current_root = tmp_path / "current"
        current_root.mkdir()
        ledger = store(current_root, VerifiedUnitAuthority())
        ledger.initialize(op())
        activation = ReleaseActivation(
            release_id=m.release.release_id,
            manifest_ref=candidate.manifest_ref,
            registry_ref=candidate.registry_ref,
            acceptance_ref=proof,
        )
        bad = ReleaseSwitch(
            expected_revision=0,
            operation=op("bad"),
            activation=activation.model_copy(
                update={"acceptance_ref": ref("release-acceptance/1", "other")}
            ),
        )
        before = (current_root / "system-current.json").read_bytes()
        with pytest.raises(OwnershipConflict):
            ledger.activate(bad)
        assert (current_root / "system-current.json").read_bytes() == before
        changed = ledger.activate(
            ReleaseSwitch(
                expected_revision=0, operation=op("accepted"), activation=activation
            )
        )
        assert changed.active == activation and changed.revision == 1
        assert store(current_root).read(op("reopen")) == changed
    finally:
        writable(tmp_path)
