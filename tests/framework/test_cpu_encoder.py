"""File/package preflight, exact batch reuse, failures and close behavior."""

import os
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.retrieval.cpu_encoder import CpuEncoder
from lab_generate_skill.adapters.retrieval.encoder_files import verify_encoder
from lab_generate_skill.domain.encoding import EncoderFile, EncoderFiles, EncoderConfig
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)

from encoder_fixtures import files, config, control, Loader
from test_atomic_snapshot import flatten


def test_load_once_exact_whole_batch_only_and_close(tmp_path: Path) -> None:
    loader = Loader()
    backend = CpuEncoder(tmp_path, files(tmp_path), config(), loader=loader)
    first = backend.score(("a", "b"), "a", control())
    second = backend.score(("a", "b"), "b", control())
    reordered = backend.score(("b", "a"), "b", control())
    subset = backend.score(("b",), "b", control())
    assert not first.documents_reused and second.documents_reused
    assert first.document_vectors_sha256 == second.document_vectors_sha256
    assert first.documents_sha256 != reordered.documents_sha256
    assert not reordered.documents_reused and not subset.documents_reused
    assert first.scores == (1.0, 0.0) and second.scores == (0.0, 1.0)
    assert loader.calls == 1 and loader.model.calls == [
        ("a", "b"),
        ("a",),
        ("b",),
        ("b", "a"),
        ("b",),
        ("b",),
        ("b",),
    ]
    backend.close(control())
    backend.close(control())
    with pytest.raises(OwnershipConflict):
        backend.score(("a",), "a", control())


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "..",
        "/absolute",
        "a/../b",
        "a//b",
        ".cache/file",
        "a\\b",
        "a\x00b",
        "a\nb",
    ],
)
def test_unsafe_member_names(path: str) -> None:
    with pytest.raises(ValidationError):
        EncoderFile(path=path, sha256="0" * 64, size_bytes=0)


@pytest.mark.parametrize("kind", ["missing", "duplicate", "order"])
def test_manifest_requires_complete_canonical_inventory(
    tmp_path: Path, kind: str
) -> None:
    manifest = files(tmp_path)
    value = (
        manifest.files[:-1]
        if kind == "missing"
        else (
            (*manifest.files, manifest.files[0])
            if kind == "duplicate"
            else tuple(reversed(manifest.files))
        )
    )
    with pytest.raises(ValidationError):
        EncoderFiles(files=value)


@pytest.mark.parametrize(
    "kind", ["missing", "changed", "extra", "link", "fifo", "package"]
)
def test_preflight_rejects_changed_assets_before_model_load(
    tmp_path: Path, kind: str
) -> None:
    manifest = files(tmp_path)
    settings = config()
    path = tmp_path / "model.safetensors"
    loader = Loader()
    if kind == "missing":
        path.unlink()
    elif kind == "changed":
        path.write_bytes(b"wrong")
    elif kind == "extra":
        (tmp_path / "extra.json").write_text("{}")
    elif kind in ("link", "fifo"):
        path.unlink()
        if kind == "link":
            path.symlink_to(tmp_path / "config.json")
        else:
            os.mkfifo(path)
    else:
        settings = settings.model_copy(
            update={
                "packages": (
                    settings.packages[0].model_copy(update={"version": "wrong"}),
                    *settings.packages[1:],
                )
            }
        )
    backend = CpuEncoder(tmp_path, manifest, settings, loader=loader)
    with pytest.raises(EvidenceIntegrityError):
        backend.score(("doc",), "query", control())
    assert loader.calls == 0
    with pytest.raises(OwnershipConflict):
        backend.score(("doc",), "query", control())


@pytest.mark.parametrize("documents", [None, [], (), (" ",), ("x", 1), ("x",) * 101])
def test_invalid_documents_have_no_load_effect(
    tmp_path: Path, documents: object
) -> None:
    loader = Loader()
    backend = CpuEncoder(tmp_path, files(tmp_path), config(), loader=loader)
    with pytest.raises(ValueError):
        backend.score(cast(tuple[str, ...], documents), "query", control())
    assert loader.calls == 0
    assert backend.score(("valid",), "query", control()).scores


@pytest.mark.parametrize("query", [None, True, 12, "", "  "])
def test_invalid_query_before_load(tmp_path: Path, query: object) -> None:
    loader = Loader()
    backend = CpuEncoder(tmp_path, files(tmp_path), config(), loader=loader)
    with pytest.raises(ValueError):
        backend.score(("document",), cast(str, query), control())
    assert loader.calls == 0


@pytest.mark.parametrize("fault", ["shape", "zero", "nan", "inf", "raise"])
def test_bad_model_output_closes_instance_without_retry(
    tmp_path: Path, fault: str
) -> None:
    loader = Loader()
    loader.model.bad = fault
    backend = CpuEncoder(tmp_path, files(tmp_path), config(), loader=loader)
    with pytest.raises(RuntimeError):
        backend.score(("document",), "query", control())
    loader.model.bad = None
    with pytest.raises(OwnershipConflict):
        backend.score(("document",), "query", control())
    assert loader.calls == 1 and len(loader.model.calls) == 1


def test_primary_read_and_cleanup_errors_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = files(tmp_path)
    settings = config()
    realclose = os.close

    def fail_read(fd: int, size: int) -> bytes:
        raise OSError("primary read")

    def fail_close(fd: int) -> None:
        realclose(fd)
        raise OSError("cleanup close")

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "read", fail_read)
        scoped.setattr(os, "close", fail_close)
        with pytest.raises(BaseExceptionGroup) as caught:
            verify_encoder(tmp_path, manifest, settings, control())
    assert [str(e) for e in flatten(caught.value)] == ["primary read", "cleanup close"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("cpu_threads", True),
        ("cpu_threads", 0),
        ("max_documents", 5),
        ("batch_size", 32.0),
        ("dimensions", 384.0),
        ("packages", ()),
    ],
)
def test_config_constants_and_resource_bounds(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        EncoderConfig.model_validate(config().model_copy(update={field: value}))


def test_fork_identity_rejected_before_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loader = Loader()
    backend = CpuEncoder(tmp_path, files(tmp_path), config(), loader=loader)
    pid = os.getpid()
    monkeypatch.setattr(os, "getpid", lambda: pid + 1)
    with pytest.raises(OwnershipConflict):
        backend.score(("doc",), "query", control())
    assert loader.calls == 0


@pytest.mark.parametrize("budget", [2, 3, 4])
def test_utf8_input_byte_budget_boundary(tmp_path: Path, budget: int) -> None:
    loader = Loader()
    backend = CpuEncoder(
        tmp_path,
        files(tmp_path),
        config().model_copy(update={"max_input_bytes": budget}),
        loader=loader,
    )
    if budget < 4:
        with pytest.raises(ValueError, match="byte budget"):
            backend.score(("é",), "ab", control())
        assert loader.calls == 0
    else:
        assert backend.score(("é",), "ab", control()).scores


def test_cancellation_after_encode_discards_model_and_cache(tmp_path: Path) -> None:
    import numpy as np
    from numpy.typing import NDArray
    from encoder_fixtures import NumericModel
    from test_run_journal import CancelSwitch, command
    from lab_generate_skill.adapters.clock import SystemClock
    from lab_generate_skill.domain.lifecycle import CancellationRef
    from lab_generate_skill.runtime.lifecycle import OperationGuards

    switch = CancelSwitch()

    class CancellingModel(NumericModel):
        def encode(
            self,
            sentences: list[str],
            *,
            normalize_embeddings: bool,
            batch_size: int,
            show_progress_bar: bool,
        ) -> NDArray[np.float32]:
            result = super().encode(
                sentences,
                normalize_embeddings=normalize_embeddings,
                batch_size=batch_size,
                show_progress_bar=show_progress_bar,
            )
            switch.cancelled = True
            return result

    op = command().model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="unit", run_id="run", owner_id="owner"
            )
        }
    )
    guard = OperationGuards(SystemClock(), switch).bind(op)
    loader = Loader(CancellingModel())
    backend = CpuEncoder(tmp_path, files(tmp_path), config(), loader=loader)
    with pytest.raises(OperationStopped):
        backend.score(("doc",), "query", guard)
    with pytest.raises(OwnershipConflict):
        backend.score(("doc",), "query", control())
    assert len(loader.model.calls) == 1


def test_lock_wait_timeout_does_not_disturb_running_encoder(tmp_path: Path) -> None:
    import threading
    from datetime import datetime, timedelta, timezone
    import numpy as np
    from numpy.typing import NDArray
    from encoder_fixtures import NumericModel
    from test_run_journal import CancelSwitch, command
    from lab_generate_skill.adapters.clock import SystemClock
    from lab_generate_skill.runtime.lifecycle import OperationGuards

    entered = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    class HeldModel(NumericModel):
        def encode(
            self,
            sentences: list[str],
            *,
            normalize_embeddings: bool,
            batch_size: int,
            show_progress_bar: bool,
        ) -> NDArray[np.float32]:
            if not self.calls:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Unit test release missing")
            return super().encode(
                sentences,
                normalize_embeddings=normalize_embeddings,
                batch_size=batch_size,
                show_progress_bar=show_progress_bar,
            )

    loader = Loader(HeldModel())
    backend = CpuEncoder(tmp_path, files(tmp_path), config(), loader=loader)

    def work() -> None:
        try:
            backend.score(("doc",), "query", control())
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=work)
    worker.start()
    try:
        assert entered.wait(5)
        op = command().model_copy(
            update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=0.05)}
        )
        guard = OperationGuards(SystemClock(), CancelSwitch()).bind(op)
        with pytest.raises(OperationStopped, match="DEADLINE_EXCEEDED"):
            backend.score(("other",), "query", guard)
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive() and not errors and loader.calls == 1
    assert backend.score(("doc",), "new query", control()).documents_reused
    backend.close(control())
