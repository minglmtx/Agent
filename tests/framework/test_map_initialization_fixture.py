"""Preflight exact controlled route, scripts and installed factory before Chromium."""

from pathlib import Path
import re
import subprocess
from urllib.request import urlopen
from urllib.error import HTTPError
import pytest
from lab_generate_skill.bootstrap.browser_engine import build_browser_engine
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.sites.map.browser_initialization import (
    MapNativeBrowserInitializer,
)
from lab_generate_skill.sites.map.native_view_scripts import READ, READINESS
from lab_generate_skill.sites.map.tasks.overlay_spec import START
from map_initialization_actual_fixtures import (
    readiness_document,
    bind_native,
    DOCUMENT_TARGET,
)
from map_native_route_actual import server_fixture
from test_map_browser_installed import selected_resource
from browsergym_fixtures import LoopbackAuthority
from test_site_storage_admission import LiveGuard
from generator_worker_fixtures import unit_guard
from test_slurm_commands import guard


def test_selected_readiness_fixture_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import playwright

    node = Path(playwright.__file__).parent / "driver/node"
    document, assets = readiness_document()
    scripts = re.findall(rb"<script>(.*?)</script>", document, re.S)
    for script in [
        *scripts,
        *(("const reader = " + s + ";").encode() for s in (READ, READINESS)),
    ]:
        result = subprocess.run(
            [str(node), "--check"],
            input=script,
            capture_output=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode()
    with server_fixture(
        "batch", document=document, assets=assets, document_target=DOCUMENT_TARGET
    ) as fixture:
        with urlopen(fixture.origin + DOCUMENT_TARGET, timeout=5) as response:
            assert (
                response.headers["Content-Type"].startswith("text/html")
                and response.read() == document
            )
        with pytest.raises(HTTPError) as caught:
            urlopen(fixture.origin + "/", timeout=5)
        assert (
            caught.value.code == 404
            and fixture.documents == 1
            and not fixture.native_calls
        )
        c = selected_resource(tmp_path, monkeypatch, fixture.origin + "/", None)
        bind_native(c, fixture.origin + "/")
        engine = build_browser_engine(
            c.spec.configuration,
            LoopbackAuthority(),
            SystemClock(),
            worker_guard=LiveGuard(unit_guard(c.spec.slurm.parent.writer, guard())),
        )
        assert isinstance(engine.initializer, MapNativeBrowserInitializer)
        assert engine.spec.task.start_url == fixture.origin + START
        assert engine.state == "new" and not c.channels
        assert c.spec.configuration.map_inputs is not None
        assert not Path(c.spec.configuration.map_inputs.plan.private_root).exists()
