"""Production publication/readback consumers use one complete initial input read."""

from pathlib import Path
from collections import Counter
import json
import pytest
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.domain.preparation import PreparationReceipt
from lab_generate_skill.domain.state_scope import StateCommitUnconfirmed
from lab_generate_skill.ports.lifecycle import OperationControl
from initial_observation_fixtures import initial_case
from test_slurm_commands import guard


def test_complete_publication_consumes_one_graph_and_retains_exact_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        reads: list[EvidenceRef] = []
        original = c.records.store.read

        def observe(reference: EvidenceRef, control: OperationControl) -> bytes:
            reads.append(reference)
            return original(reference, control)

        monkeypatch.setattr(c.records.store, "read", observe)
        ref = c.records.publish(c.selection, c.op)
        value = c.records.load(c.selection, ref, c.op)
        inputs = c.records.reader.load(c.selection, c.op, guard())
        preparation = c.records.reader.reads.parse(
            c.selection.preparation.preparation_ref,
            "preparation-receipt/1",
            PreparationReceipt,
            guard(),
        )
        legacy = Counter(reads)
        calls = c.authority.calls
        reads.clear()
        complete = c.records.publish_complete(c.selection, c.op)
        current = Counter(reads)
        assert (
            complete.reference,
            complete.value,
            complete.inputs,
            complete.preparation,
        ) == (ref, value, inputs, preparation)
        assert c.authority.calls == calls + 2
        assert sum(current.values()) < sum(legacy.values())
        assert current[c.selection.preparation.preparation_ref] == 1
        assert c.prepared.browser.channels[0].engine.calls == ["start"]
        (tmp_path / "initial-read-counts.json").write_text(
            json.dumps(
                {
                    "scope": "same producer fixture publication/readback/baseline inputs; no real worker timing",
                    "legacy_reads": sum(legacy.values()),
                    "current_reads": sum(current.values()),
                    "removed_reads": sum(legacy.values()) - sum(current.values()),
                    "legacy_unique": len(legacy),
                    "current_unique": len(current),
                },
                indent=2,
            )
            + "\n"
        )


@pytest.mark.parametrize("fault", ["revoked", "missing", "corrupt", "cancel"])
def test_complete_publication_post_write_failure_keeps_reference_and_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        original = c.records.store.put
        delegate = c.records.controls.bind(c.op)
        stopped = False

        class Control:
            def checkpoint(self) -> float:
                if stopped and fault == "cancel":
                    raise RuntimeError("Cancelled after initial publication")
                return delegate.checkpoint()

            def wait(self, seconds: float) -> None:
                delegate.wait(seconds)

        def committed(
            data: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            nonlocal stopped
            reference = original(data, metadata, control)
            if metadata.content_schema == "initial-state-checks/1":
                stopped = True
                if fault == "revoked":
                    c.authority.denied = True
                if fault in ("missing", "corrupt"):
                    path = tmp_path / "site/evidence/blobs" / reference.sha256
                    if fault == "missing":
                        path.unlink()
                    else:
                        path.write_bytes(b"corrupt")
            return reference

        with monkeypatch.context() as patch:
            patch.setattr(c.records.store, "put", committed)
            patch.setattr(c.records.controls, "bind", lambda op: Control())
            with pytest.raises(StateCommitUnconfirmed) as caught:
                c.records.publish_complete(c.selection, c.op)
        expected = {
            "revoked": PermissionError,
            "missing": EvidenceNotFound,
            "corrupt": EvidenceIntegrityError,
            "cancel": RuntimeError,
        }[fault]
        assert isinstance(caught.value.__cause__, expected)
        assert caught.value.reference.content_schema == "initial-state-checks/1"
        c.authority.denied = False
        assert c.prepared.browser.channels[0].engine.calls == ["start"]
