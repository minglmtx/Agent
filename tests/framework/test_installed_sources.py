"""Real installed subprocess checks, separate from full release publication."""

import json
import hashlib
import shutil
import tempfile
from pathlib import Path

import pytest

from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import (
    installed_worker as installed_worker,
    checked_command,
)


def probe(fixture: InstalledFixture, tmp_path: Path, fault: str) -> bytes:
    data = fixture.manifest.model_dump()
    extra_root: Path | None = None
    if fault == "foreign_pinned_module":
        extra_root = Path(
            tempfile.mkdtemp(prefix="declared-extra-", dir=fixture.workspace)
        )
        package = extra_root / "lab_generate_skill"
        package.mkdir()
        raw = b"MARKER = 1\n"
        source = package / "old_component.py"
        source.write_bytes(raw)
        source.chmod(0o444)
        package.chmod(0o555)
        extra_root.chmod(0o555)
        data["artifacts"] += (
            {
                "artifact_id": "extra-code",
                "root": str(extra_root),
                "files": (
                    {
                        "path": "lab_generate_skill/old_component.py",
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "size_bytes": len(raw),
                        "executable": False,
                    },
                ),
            },
        )
        for component in data["components"]:
            if component["component_id"] == "code":
                component["artifact_ids"] += ("extra-code",)
    if fault == "python_pin":
        data["artifacts"][1]["files"][0]["sha256"] = "f" * 64
    if fault in ("source_pin", "unloaded_source_pin"):
        target = (
            "lab_generate_skill/__init__.py"
            if fault == "source_pin"
            else "lab_generate_skill/domain/optional_policies.py"
        )
        for entry in data["artifacts"][0]["files"]:
            if entry["path"] == target:
                entry["sha256"] = "f" * 64
    if fault == "metadata_pin":
        for entry in data["artifacts"][0]["files"]:
            if entry["path"].endswith(".dist-info/METADATA"):
                entry["sha256"] = "f" * 64
    manifest = tmp_path / "release.json"
    manifest.write_text(json.dumps(data))
    program = Path(__file__).with_name("installed_source_probe.py").read_text()
    flags = (
        ["-B"]
        if fault == "not_isolated"
        else ["-I"] if fault == "bytecode_enabled" else ["-I", "-B"]
    )
    package = Path(fixture.manifest.artifacts[0].root) / "lab_generate_skill"
    late_source = package / "__init__.py"
    late_original = (
        late_source.read_bytes() if fault == "late_loaded_source_change" else None
    )
    cache = package / "unexpected.pyc"
    if fault == "bytecode_cache":
        package.chmod(0o755)
        cache.write_bytes(b"stale bytecode")
        cache.chmod(0o444)
        package.chmod(0o555)
    try:
        return checked_command(
            [
                str(fixture.executable),
                *flags,
                "-c",
                program,
                str(manifest),
                str(fixture.workspace),
                fault,
            ],
            cwd=tmp_path,
        )
    finally:
        if extra_root is not None:
            extra_root.chmod(0o755)
            (extra_root / "lab_generate_skill").chmod(0o755)
            shutil.rmtree(extra_root)
        if fault == "bytecode_cache":
            package.chmod(0o755)
            cache.unlink()
            package.chmod(0o555)
        if late_original is not None:
            late_source.chmod(0o644)
            late_source.write_bytes(late_original)
            late_source.chmod(0o444)


def test_actual_installed_sources_and_repeat_are_pinned(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", "/old/checkout")
    result = json.loads(probe(installed_sources, tmp_path, "none"))
    assert result["executable"] == str(installed_sources.executable)
    assert result["release_id"] == installed_sources.manifest.release_id
    assert result["distribution_version"] == "0.1.0"
    assert result["modules"] and all(
        Path(item["filename"]).is_relative_to(result["package_root"])
        for item in result["modules"]
    )


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("python_pin", "content differs"),
        ("source_pin", "content differs"),
        ("unloaded_source_pin", "content differs"),
        ("metadata_pin", "content differs"),
        ("not_isolated", "requires -I -B"),
        ("bytecode_enabled", "requires -I -B"),
        ("alternate_path", "alternate search path"),
        ("inconsistent_origin", "inconsistent source origin"),
        ("main_origin", "inconsistent source origin"),
        ("duplicate_main", "duplicate loaded identities"),
        ("foreign_module", "outside installed package root"),
        ("foreign_pinned_module", "outside installed package root"),
        ("bytecode_cache", "inventory differs"),
        ("late_import", "changed during verification"),
        ("late_loaded_source_change", "changed during verification"),
        ("cancelled", "test source check expired"),
    ],
)
def test_wrong_installation_or_interruption_never_returns_receipt(
    installed_sources: InstalledFixture, tmp_path: Path, fault: str, reason: str
) -> None:
    with pytest.raises(RuntimeError, match=reason):
        probe(installed_sources, tmp_path, fault)


def test_each_fresh_verifier_hashes_all_code_once_per_package_file(
    installed_sources: InstalledFixture, tmp_path: Path
) -> None:
    result = json.loads(probe(installed_sources, tmp_path, "hash_counts"))
    code = installed_sources.manifest.artifacts[0]
    package_files = [f for f in code.files if f.path.startswith("lab_generate_skill/")]
    assert package_files
    assert result["package_files"] == len(package_files)
    assert result["package_hash_call_counts"] == [1]
    assert (
        result["all_code_hashed_each_call"]
        and result["second_call_repeated_all_hashes"]
    )
    assert result["executable_hash_calls"] == 1
    # Outside-package metadata keeps its original explicit plus full-pass check.
    for name in ("METADATA", "WHEEL", "RECORD"):
        assert result["metadata_hash_calls"][name] == [2]
