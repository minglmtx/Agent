"""Original Web Ruby, fixed program compile and actual exclusive full-file output.

Payload is synthetic; no Rails, geographic DB, site admission or Actor here.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import traceback
from typing import Any
import pytest
from lab_generate_skill.adapters.map_runtime.database_export import (
    NativeMapDatabaseExportFiles,
)
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.domain.map_runtime_inputs import IMAGE_PINS
from lab_generate_skill.domain.map_database_export import MapDatabaseExport
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.sites.map.native_database_program import reference_program
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from map_frontend_fixtures import frontend_case
from map_database_capture_fixtures import BOUNDS, payload
from test_slurm_commands import guard


def test_native_output_fixture_preflight() -> None:
    program = reference_program(BOUNDS, "request0", 16 * 1024**2).decode()
    assert program.count("serialized = JSON.generate(payload)") == 1
    assert "File::EXCL" in program and "file.chmod(0400)" in program
    assert program.count("file.fsync") == 1 and program.count("directory.fsync") == 1
    assert (
        BoundedMapStartupControls().bind(guard(600), "database_reference").checkpoint()
        <= 180
    )
    assert (
        BoundedMapStartupControls().bind(guard(0.1), "database_reference").checkpoint()
        <= 0.1
    )


def test_actual_original_ruby_complete_output_and_exclusive_budget_failure() -> None:
    root = Path(tempfile.mkdtemp(prefix="lab-map-database-output-", dir="/tmp"))
    out = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    facts: dict[str, Any] = dict(
        actual_rails=False,
        actual_database=False,
        actual_actor=False,
        synthetic_payload=True,
        paid_calls=0,
        root=str(root),
    )
    success = False
    try:
        spec, _, _ = frontend_case(root)
        state = Path(spec.state_root("frontend"))
        state.mkdir(parents=True, mode=0o700)
        files = NativeMapDatabaseExportFiles()
        program = reference_program(BOUNDS, "request0", 16 * 1024**2)
        plan = MapDatabaseExport(
            spec=spec,
            label="request0",
            max_output_bytes=16 * 1024**2,
            program=ReleaseFile(
                path="reference.rb",
                sha256=hashlib.sha256(program).hexdigest(),
                size_bytes=len(program),
                executable=False,
            ),
        )
        files.prepare(plan, program, guard())
        sha, size = IMAGE_PINS["web"]
        image = (
            Path("/anvme/workspace/r102bf10-lab-generate-skill/assets/webarena/map/web")
            / sha
            / "web.sif"
        )
        assert image.resolve(strict=True) == image and image.stat().st_size == size
        checksum = hashlib.sha256()
        with image.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024**2), b""):
                checksum.update(chunk)
        assert checksum.hexdigest() == sha
        prefix = (
            "/usr/bin/apptainer",
            "exec",
            "--cleanenv",
            "--containall",
            "--no-home",
            "--no-mount",
            "bind-paths,hostfs,cwd",
            "--bind",
            str(state) + ":/state",
            "--pwd",
            "/state",
            str(image),
            "ruby",
        )
        commands = CheckedNativeCommands(ProcessRunner(max_output_bytes=65536))
        assert (
            commands.run(prefix + ("-c", plan.container_program), guard(30)).strip()
            == b"Syntax OK"
        )
        value = payload()
        value["nodes"][0]["tags"]["large"] = "x" * (8 * 1024**2)
        body = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
        (state / "payload.json").write_bytes(body)
        materialization = program.decode().split(
            "serialized = JSON.generate(payload)", 1
        )[1]
        fixture = (
            'require "json"\npayload = JSON.parse(File.binread("/state/payload.json"))\nserialized = JSON.generate(payload)'
            + materialization
        )
        (state / "output-fixture.rb").write_text(fixture)
        assert commands.run(prefix + ("/state/output-fixture.rb",), guard(30)) == b""
        data = files.read(plan, guard(30))
        assert data == body and len(data) > 8 * 1024**2
        output = Path(plan.host_directory) / plan.output_name
        initial = output.stat()
        # Deliberate illegal duplicate input against a known completed fixture.
        with pytest.raises(CommandFailure) as duplicate:
            commands.run(prefix + ("/state/output-fixture.rb",), guard(30))
        assert b"File exists" in duplicate.value.capture.stderr
        (out / "database-output-duplicate-stderr.bin").write_bytes(
            duplicate.value.capture.stderr
        )
        assert output.read_bytes() == body and output.stat().st_ino == initial.st_ino
        low = (
            reference_program(BOUNDS, "limited", 1)
            .decode()
            .split("serialized = JSON.generate(payload)", 1)[1]
        )
        (state / "native-reference-limited").mkdir(mode=0o700)
        (state / "budget-fixture.rb").write_text(
            'require "json"\npayload = {}\nserialized = JSON.generate(payload)' + low
        )
        with pytest.raises(CommandFailure) as budget:
            commands.run(prefix + ("/state/budget-fixture.rb",), guard(30))
        assert b"byte budget exceeded" in budget.value.capture.stderr
        (out / "database-output-budget-stderr.bin").write_bytes(
            budget.value.capture.stderr
        )
        assert not (
            state / "native-reference-limited/osm-expanded-limited.json"
        ).exists()
        facts.update(
            image_sha256=sha,
            program_sha256=plan.program.sha256,
            output_bytes=len(data),
            output_sha256=hashlib.sha256(data).hexdigest(),
            output_mode=oct(initial.st_mode & 0o777),
            normal_stdout_bytes=0,
            duplicate_returncode=duplicate.value.capture.returncode,
            budget_returncode=budget.value.capture.returncode,
        )
        success = True
    except BaseException as error:
        (out / "database-output-failure.txt").write_text(
            "".join(traceback.format_exception(error))
        )
        raise
    finally:
        if success:
            shutil.rmtree(root)
        facts.update(passed=success, root_retained=not success)
        (out / "database-output-result.json").write_text(
            json.dumps(facts, indent=2) + "\n"
        )
