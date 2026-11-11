"""Same actual adapters, then a separate read-only process; effects are doubles."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites import step as site_step
from lab_generate_skill.adapters.browsergym import step as browser_step
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from map_registered_worker_fixtures import RegisteredMapCase
from map_qualification_fixtures import configure_qualification
from map_qualified_source_native import MapQualifiedSource
from map_source_inputs import MapSourceInputs
from lab_generate_skill.sites.map.tasks.overlay_spec import NativeOverlaySpec
from map_browser_storage_fixtures import collection_spec
from map_browser_collection_fixtures import CollectionCase
from map_terminal_fixtures import select_original
from map_actual_actor_assembly_fixtures import run_combination
from map_closed_review_fixtures import closed_proof
from test_site_resource import enter, inspect
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
import prepared_browser_native


@pytest.mark.parametrize(
    "mode", ["native", "batch", "protocol-native", "protocol-batch"]
)
def test_actual_adapters_then_separate_closed_readonly_review(
    registered_map: RegisteredMapCase,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    protocol = mode.startswith("protocol-")
    mode = mode.removeprefix("protocol-")
    c = registered_map
    assert isinstance(c.private, NativeOverlaySpec)
    proof = select_original(c)
    spec_ref, _ = configure_qualification(c, monkeypatch)
    sources = collection_spec(
        c.workspace / "declared-sources", c.resource.op
    ).original_sources
    inputs = MapSourceInputs(c.configuration, c.private, sources, spec_ref, proof)
    browsers: list[CollectionCase] = []
    closed_proof(site_step, monkeypatch)

    def browser(root: Path, patch: pytest.MonkeyPatch, **kwargs: Any) -> Any:
        b = CollectionCase(
            root,
            patch,
            owner=c.scope.owner,
            store=c.resource.evidence,
            workspace=c.workspace,
        )
        cfg, token = kwargs["config"], kwargs["declared_token"]
        assert kwargs["real_step"] is True
        b.configuration, b.plan = cfg, cfg.map_inputs.plan
        b.resource.spec = BrowserResourceSpec.model_validate(
            b.resource.spec.model_copy(update={"token": token, "configuration": cfg})
        )
        closed_proof(browser_step, patch)
        browsers.append(b)
        c.observer = "controller"
        return b.resource

    monkeypatch.setattr(prepared_browser_native, "resource_case", browser)
    monkeypatch.setattr(
        prepared_browser_native,
        "EngineeringTreeAuthority",
        lambda store: browsers[-1].resource.authority,
    )
    with enter(c.resource) as site:
        source = MapQualifiedSource(
            c.resource, site, inputs, allowed_actions=("click", "send_msg_to_user")
        )
        c.binding, c.task_recovery = (
            source.native.binding_ref,
            source.native.recovery_ref,
        )
        facts = run_combination(
            c, source, browsers, monkeypatch, mode=mode, terminal=protocol
        )
    facts["resource_record"] = inspect(c.resource).model_dump(mode="json")
    facts["evidence_root"] = str(c.workspace / "evidence")
    facts["original_process"] = os.getpid()
    context = c.workspace / "closed-review-context.json"
    original = json.dumps(facts).encode()
    context.write_bytes(original)
    env = dict(os.environ)
    framework = Path(__file__).resolve().parent
    env["PYTHONPATH"] = str(framework) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(framework / "map_closed_review_probe.py"),
            str(context),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == dict(
        separate_process=True, evaluation="failure", reset="safe", read_only=True
    )
    assert context.read_bytes() == original
