"""Shared installation contract and real isolated verification, without models."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
)
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from generator_installation_fixtures import (
    unit_declaration,
    unit_verifier,
    installed_declaration,
)
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_slurm_commands import guard


def shared(fixture: InstalledFixture) -> ReleaseInstallation:
    old = installed_declaration(fixture)
    return ReleaseInstallation.model_validate(
        {**old.model_dump(), "schema_version": "release-installation/1"}
    )


def test_generator_versioned_bytes_preserved_by_shared_fields() -> None:
    old = unit_declaration()
    expected = {
        "schema_version": "generator-installation/1",
        "manifest_ref": old.manifest_ref.model_dump(mode="json"),
        "manifest": old.manifest.model_dump(mode="json"),
        "workspace_root": old.workspace_root,
        "python_executable": old.python_executable,
    }
    assert old.model_dump_json() == json.dumps(
        expected, ensure_ascii=False, separators=(",", ":")
    )
    projected = ReleaseInstallation.model_validate(
        {
            **expected,
            "manifest_ref": old.manifest_ref,
            "manifest": old.manifest,
            "schema_version": "release-installation/1",
        }
    )
    assert projected.model_dump(exclude={"schema_version"}) == old.model_dump(
        exclude={"schema_version"}
    )
    observed = unit_verifier(old, guard())
    expected_observed = {
        "schema_version": "generator-installed-sources/1",
        "release_id": observed.release_id,
        "manifest_sha256": observed.manifest_sha256,
        "executable": observed.executable,
        "package_root": observed.package_root,
        "distribution_version": observed.distribution_version,
        "modules": [m.model_dump(mode="json") for m in observed.modules],
    }
    assert observed.model_dump_json() == json.dumps(
        expected_observed, ensure_ascii=False, separators=(",", ":")
    )
    common = InstalledReleaseSources.model_validate(
        {**observed.model_dump(), "schema_version": "installed-release-sources/1"}
    )
    assert common.model_dump(exclude={"schema_version"}) == observed.model_dump(
        exclude={"schema_version"}
    )


@pytest.mark.parametrize(
    "version", [None, "", "generator-installation/1", "release-installation/0", 1]
)
def test_shared_declaration_rejects_wrong_or_role_specific_version(
    version: object,
) -> None:
    with pytest.raises(ValueError):
        ReleaseInstallation.model_validate(
            {**unit_declaration().model_dump(), "schema_version": version}
        )


PROGRAM = """
import sys
from datetime import datetime,timedelta,timezone
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.adapters.releases.installation import verify_release_installation
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
class NoCancellation:
    def is_cancelled(self,reference): raise AssertionError('no cancellation provider')
assert 'lab_generate_skill.domain.generator_installation' not in sys.modules
assert 'lab_generate_skill.adapters.models.generator_installation' not in sys.modules
declaration=ReleaseInstallation.model_validate_json(sys.stdin.buffer.read())
op=OperationContext(operation_id='inspect-release',run_id='engineering',owner_id='controller',deadline=datetime.now(timezone.utc)+timedelta(seconds=30))
try:
    result=verify_release_installation(declaration,OperationGuards(SystemClock(),NoCancellation()).bind(op))
except BaseException as error:
    print(type(error).__name__,file=sys.stderr)
    raise SystemExit(7)
assert 'lab_generate_skill.domain.generator_installation' not in sys.modules
print(result.model_dump_json())
"""


@pytest.mark.parametrize("fault", [None, "python", "source", "workspace"])
def test_actual_shared_release_entry_without_generator_dependency(
    installed_sources: InstalledFixture, fault: str | None
) -> None:
    declaration = shared(installed_sources)
    if fault == "python":
        declaration = declaration.model_copy(
            update={"python_executable": "/wrong/python"}
        )
    elif fault == "workspace":
        declaration = declaration.model_copy(
            update={"workspace_root": str(installed_sources.workspace / "missing")}
        )
    elif fault == "source":
        data = declaration.manifest.model_dump()
        for entry in data["artifacts"][0]["files"]:
            if entry["path"] == "lab_generate_skill/__init__.py":
                entry["sha256"] = "0" * 64
        manifest = ReleaseManifest.model_validate(data)
        reference = evidence_reference(
            manifest.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="release-manifest/1",
                visibility="private",
                producer="fixture",
            ),
        )
        declaration = declaration.model_copy(
            update={"manifest": manifest, "manifest_ref": reference}
        )
    capture = ProcessRunner().run(
        (str(installed_sources.executable), "-I", "-B", "-c", PROGRAM),
        guard(60),
        stdin_bytes=declaration.model_dump_json().encode(),
    )
    if fault is not None:
        assert capture.returncode == 7 and capture.stderr and not capture.stdout
    else:
        assert capture.returncode == 0 and not capture.stderr
        actual = InstalledReleaseSources.model_validate_json(capture.stdout)
        assert actual.release_id == declaration.manifest.release_id
        assert actual.manifest_sha256 == declaration.manifest_ref.sha256
        assert actual.executable == str(installed_sources.executable)
        assert any(
            m.name == "lab_generate_skill.adapters.releases.installation"
            for m in actual.modules
        )
