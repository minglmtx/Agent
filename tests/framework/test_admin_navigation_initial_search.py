"""Original navigation startup and pinned PHP faults; no website chain replay."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from lab_generate_skill.domain.admin_navigation_origin import AdminNavigationOrigin
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.sites.shopping_admin.initial_search import (
    INITIAL_SEARCH_HOLD_PHP,
)
from lab_generate_skill.sites.shopping_admin.service_programs import CONFIGURE, HEALTH
from test_admin_instance import instance
from test_admin_search_http import command
from search_http_fixtures import search_server
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_initial_search_program_syntax_before_startup() -> None:
    result = subprocess.run(
        command("if(false){" + INITIAL_SEARCH_HOLD_PHP + "}"),
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr.decode()


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "stop_unconfirmed",
        "ilm_stuck",
        "unsupported_version",
        "bad_json",
        "blocked",
        "initial_503",
    ],
)
def test_pinned_search_hold_confirms_exact_original_without_retrying_stop(
    fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with search_server("none" if fault == "initial_503" else fault) as (state, port):
        state.ilm = "RUNNING"
        if fault == "initial_503":
            original = state.response
            pending = True

            def not_ready(method: str, target: str) -> Any:
                nonlocal pending
                if pending:
                    pending = False
                    state.calls.append((method, target))
                    return 503, {"error": "not ready"}
                return original(method, target)

            monkeypatch.setattr(state, "response", not_ready)
        result = subprocess.run(
            command(INITIAL_SEARCH_HOLD_PHP, str(port), "0.35"),
            capture_output=True,
            timeout=15,
        )
        if fault in ("none", "initial_503"):
            assert result.returncode == 0, result.stderr.decode()
            assert (
                result.stdout == b"search-lifecycle-stopped" and state.ilm == "STOPPED"
            )
        else:
            assert result.returncode == 2, (result.stdout, result.stderr)
            error = json.loads(result.stderr.splitlines()[-1])
            assert error["stage"] in ("readiness", "stop_ilm", "confirm_stopped")
        writes = [c for c in state.calls if c[0] != "GET"]
        assert writes == (
            []
            if fault in ("unsupported_version", "bad_json", "blocked")
            else [("POST", "/_ilm/stop")]
        )
        assert not state.deleted and not state.deleted_streams and not state.restored


@pytest.mark.parametrize("fault", ["none", "wrong-ack", "cancel", "native-failure"])
def test_original_navigation_instance_holds_search_before_backend_and_closes_partial_start(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    site, allocator, group, events = instance(node_path)
    site.plan = site.plan.model_copy(
        update={
            "navigation_origin": AdminNavigationOrigin(
                endpoint="http://127.0.0.1:12001/admin"
            )
        }
    )
    original = site.commands.run
    stages = []

    def run(argv: tuple[str, ...], control: Any) -> bytes:
        if INITIAL_SEARCH_HOLD_PHP in argv:
            stages.append("hold")
            assert group.names == ["mysql", "redis", "search"]
            assert argv[-2] == "12004"
            if fault == "cancel":
                raise OperationStopped("CANCELLED", "initial-search")
            if fault == "native-failure":
                raise OSError("Initial search native failure")
            return b"search-lifecycle-stopped" if fault == "none" else b"unconfirmed"
        if HEALTH in argv:
            stages.append("health")
        if CONFIGURE in argv:
            stages.append("configure")
        return original(argv, control)

    monkeypatch.setattr(site.commands, "run", run)
    site.prepare(guard())
    assert site.spec is not None
    assert events.index("initial-search-syntax") < events.index("seed")
    assert (
        site.services is not None
        and site.services.navigation_origin == site.plan.navigation_origin
    )
    if fault == "none":
        assert site.start(guard()) == site.spec.admin_url
        assert stages[:3] == ["hold", "health", "configure"]
    else:
        expected = {
            "wrong-ack": ValueError,
            "cancel": OperationStopped,
            "native-failure": OSError,
        }[fault]
        with pytest.raises(expected):
            site.start(guard())
        assert site.state == "failed" and stages == ["hold"]
    assert len(site.stop(guard())) == (5 if fault == "none" else 3)
    assert not allocator.lease.released and group.stop_calls == 1
    before = list(stages)
    with pytest.raises(RuntimeError):
        site.start(guard())
    assert stages == before
