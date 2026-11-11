"""Probe schema/boundaries and compilation of the new PHP before large image I/O."""

import json
from typing import Any
import pytest
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from shopping_image_probe import PROBE, PATH_KEYS, SOURCE_KEYS, parse_probe
from test_admin_database_native import IMAGE
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "change",
    ["none", "missing", "bool", "source", "effect", "extra", "duplicate", "size"],
)
def test_layout_probe_strict_facts_retain_missing_prerequisites(change: str) -> None:
    value: dict[str, Any] = dict(
        schema_version="shopping-image-layout-probe/1",
        php="7.4.3",
        pdo_mysql=True,
        paths={k: True for k in PATH_KEYS},
        order_sources={k: "a" * 64 for k in SOURCE_KEYS},
        native_services_started=False,
        credentials_read=False,
    )
    if change == "missing":
        value["paths"]["database"] = False
        value["order_sources"][next(iter(SOURCE_KEYS))] = None
    elif change == "bool":
        value["pdo_mysql"] = "true"
    elif change == "source":
        value["order_sources"][next(iter(SOURCE_KEYS))] = "invalid"
    elif change == "effect":
        value["credentials_read"] = True
    elif change == "extra":
        value["caller_script"] = "never"
    raw = json.dumps(value).encode()
    if change == "duplicate":
        raw = b'{"php":"a","php":"b"}'
    elif change == "size":
        raw = b" " * 16385
    if change in ("none", "missing"):
        result = parse_probe(raw)
        assert result == value
    else:
        with pytest.raises(ValueError):
            parse_probe(raw)


def test_new_php_probe_compiles_using_accepted_image_without_services() -> None:
    # Reuse the immutable Admin image's installed PHP only for this new script's
    # syntax gate. No extraction, database, web server or model is started.
    image = IMAGE.resolve(strict=True)
    capture = ProcessRunner(max_output_bytes=16384).run(
        (
            "/usr/bin/apptainer",
            "exec",
            "--cleanenv",
            "--containall",
            "--no-home",
            "--no-mount",
            "bind-paths,hostfs,cwd",
            "--pwd",
            "/",
            str(image),
            "php",
            "-r",
            "if(false){" + PROBE + "}",
        ),
        guard(20),
    )
    assert capture.returncode == 0, capture.stderr.decode(errors="replace")
