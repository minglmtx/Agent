"""Real fixed-client framing regression on the complete PHP contents reader.

Native format source: next-check-4913920/admin-database-native.json. SQL/search
remain explicit content fixtures; this does not qualify a live source instance.
"""

import hashlib
import json
from pathlib import Path
import pytest
from admin_navigation_contents_fixtures import SQL, measured_server, run_measurement
from lab_generate_skill.sites.shopping_admin.tasks.navigation_contents_schema import (
    NavigationContentsReply,
)

MARIA = b"-- MariaDB dump 10.19  Distrib 10.6.12-MariaDB, for Linux (x86_64)\n"
BODY = SQL.split(b"\n", 1)[1]
FOOTER = b"-- Dump completed on 2026-11-04  8:55:13\n"


def test_fixed_image_producer_record_has_actual_format_and_confirmed_closure() -> None:
    path = Path(
        "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-combined-release-20261030-v1/next-check-4913920/admin-database-native.json"
    )
    raw = path.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "2e88b543119c864f028cd5535f7ad04af5ab0565aaa7861d068400345e987f64"
    )
    record = json.loads(raw)
    assert record["passed"] and record["engineering_only"]
    assert record["native_dump_format"]["first_lines"][0].encode() == MARIA
    assert record["native_dump_format"]["last_line"].encode() + b"\n" == FOOTER
    assert record["server_termination"]["state"] == "reaped"
    assert record["server_termination"]["returncode"] == 0
    assert not record["server_cleanup_errors"]


@pytest.mark.parametrize("header", [SQL.split(b"\n", 1)[0] + b"\n", MARIA])
@pytest.mark.parametrize("hour", [b"00", b"09", b" 0", b" 9", b"10", b"23"])
def test_supported_framing_keeps_raw_pin_and_only_omits_final_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    header: bytes,
    hour: bytes,
) -> None:
    with measured_server(monkeypatch) as (state, port):
        first = run_measurement(
            tmp_path / "first", port, state.record, sql=header + BODY + FOOTER
        )
        assert first.returncode == 0, first.stderr.decode()
        changed_footer = b"-- Dump completed on 2026-11-04 " + hour + b":00:00\n"
        for name in ("second", "repeated"):
            second = run_measurement(
                tmp_path / name, port, state.record, sql=header + BODY + changed_footer
            )
            assert second.returncode == 0, second.stderr.decode()
            one = NavigationContentsReply.model_validate_json(first.stdout)
            two = NavigationContentsReply.model_validate_json(second.stdout)
            assert one.database_raw_sha256 != two.database_raw_sha256
            assert one.model_dump(exclude={"database_raw_sha256"}) == two.model_dump(
                exclude={"database_raw_sha256"}
            )


@pytest.mark.parametrize(
    "fault",
    [
        "unknown_client",
        "wrong_arch",
        "missing_header",
        "empty",
        "unpadded_hour",
        "invalid_hour",
        "extra_space",
        "partial_footer",
        "trailing_sql",
        "raw_pin",
    ],
)
def test_invalid_or_incomplete_dump_refused_before_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    header, footer = MARIA, FOOTER
    if fault == "unknown_client":
        header = MARIA.replace(b"10.6.12", b"10.6.13")
    elif fault == "wrong_arch":
        header = MARIA.replace(b"x86_64", b"aarch64")
    elif fault == "missing_header":
        header = b""
    elif fault == "unpadded_hour":
        footer = FOOTER.replace(b"  8:", b" 8:")
    elif fault == "invalid_hour":
        footer = FOOTER.replace(b" 8:", b"24:")
    elif fault == "extra_space":
        footer = FOOTER.replace(b"  8:", b"   8:")
    elif fault == "partial_footer":
        footer = FOOTER.removesuffix(b"\n")
    elif fault == "trailing_sql":
        footer += b"SELECT 1;\n"
    raw = b"" if fault == "empty" else header + BODY + footer
    with measured_server(monkeypatch) as (state, port):
        result = run_measurement(
            tmp_path, port, state.record, sql=raw, wrong_pin=fault == "raw_pin"
        )
        assert result.returncode == 2 and not result.stdout and result.stderr
        assert not state.calls


def test_maria_header_and_sql_bytes_are_preserved_in_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with measured_server(monkeypatch) as (state, port):
        original = run_measurement(
            tmp_path / "original", port, state.record, sql=MARIA + BODY + FOOTER
        )
        other_header = run_measurement(
            tmp_path / "header", port, state.record, sql=SQL + FOOTER
        )
        other_sql = run_measurement(
            tmp_path / "sql",
            port,
            state.record,
            sql=MARIA + BODY.replace(b"unchanged", b"changed") + FOOTER,
        )
    assert all(p.returncode == 0 for p in (original, other_header, other_sql))
    measured = [
        NavigationContentsReply.model_validate_json(p.stdout)
        for p in (original, other_header, other_sql)
    ]
    assert len({m.database_content_sha256 for m in measured}) == 3
