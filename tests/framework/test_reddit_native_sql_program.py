"""Original interpreter compile and hash-loop control, never native DB startup."""

import hashlib
import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.sites.reddit.native_capture_program import CAPTURE
from lab_generate_skill.sites.reddit.native_sql_program import SQL
from lab_generate_skill.sites.reddit.service_commands import container
from reddit_native_program_fixture import OriginalImageCommands, prepare
from reddit_sql_control_fixture import PDO_FIXTURE
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_scripted_sql_fixture_has_no_real_connection_or_startup_entry() -> None:
    assert "new PDO(" not in PDO_FIXTURE and "exec(" not in PDO_FIXTURE


def test_original_php_compiles_entire_current_capture_without_database(
    node_path: Path,
) -> None:
    selected = prepare(node_path)
    commands = OriginalImageCommands(selected)
    assert (
        commands.run(
            container(selected, seeded=False)
            + ("/usr/local/bin/php", "-r", "if(false){" + CAPTURE + "}"),
            guard(30),
        )
        == b""
    )
    assert not (node_path / "state/postgres").exists()


@pytest.mark.parametrize("mode", ["reference", "one-new", "multiple-new"])
def test_original_php_hashes_full_and_original_rows_with_actual_new_ids(
    node_path: Path, mode: str
) -> None:
    selected = prepare(node_path)
    commands = OriginalImageCommands(selected)
    baseline = (
        None
        if mode == "reference"
        else [[1, 1], [3, 3]] if mode == "one-new" else [[1, 1]]
    )
    tail = (
        '$db=new ScriptedNativeDatabase();$value=reddit_submissions($db,["submissions"=>["id","title"]],json_decode('
        + json.dumps(json.dumps(baseline))
        + ",true,512,JSON_THROW_ON_ERROR));echo json_encode($value,JSON_THROW_ON_ERROR);"
    )
    raw = commands.run(
        container(selected, seeded=False)
        + ("/usr/local/bin/php", "-r", SQL + PDO_FIXTURE + tail),
        guard(30),
    )
    result = json.loads(raw)
    full = hashlib.sha256(
        b"a" * 32 + b"\n" + b"b" * 32 + b"\n" + b"c" * 32 + b"\n"
    ).hexdigest()
    assert result["full"] == dict(
        count=3, columns=["id", "title"], key=["id"], sha256=full
    )
    if mode == "one-new":
        old = hashlib.sha256(b"a" * 32 + b"\n" + b"c" * 32 + b"\n").hexdigest()
        assert result["original"] == dict(
            count=2, columns=["id", "title"], key=["id"], sha256=old
        )
        assert [r["id"] for r in result["added"]] == [2]
    elif mode == "multiple-new":
        assert result["original"] == result["full"] and [
            r["id"] for r in result["added"]
        ] == [2, 3]
    else:
        assert (
            result["known_id_ranges"] == [[1, 3]]
            and result["added"] == []
            and result["original"] == result["full"]
        )


@pytest.mark.parametrize("value", [True, 1.5, -1, "01", "1 OR true", None, []])
def test_actual_native_integer_helper_rejects_wrong_types_before_sql(
    node_path: Path, value: object
) -> None:
    selected = prepare(node_path)
    commands = OriginalImageCommands(selected)
    tail = (
        "reddit_integer(json_decode("
        + json.dumps(json.dumps(value))
        + ",true,512,JSON_THROW_ON_ERROR),true);"
    )
    with pytest.raises(CommandFailure):
        commands.run(
            container(selected, seeded=False)
            + ("/usr/local/bin/php", "-r", SQL + tail),
            guard(30),
        )
