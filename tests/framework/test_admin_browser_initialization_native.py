"""Real Admin login/task setup and one BrowserGym observation; leaf engineering.

Uses production site assembly/seed/browser initializer. Synthetic preparation
references and explicit test authority are not production admission or baseline.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_initialization import AdminProductInitialization
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.browsergym.login_catalog import admin_login
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.bootstrap.browser_initialization import browser_initializer
from lab_generate_skill.bootstrap.admin_description import (
    load_product_description_inputs,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_seed import AdminProductSeed
from lab_generate_skill.sites.shopping_admin.service_contract import AdminServiceSpec
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.browser_session import RawBrowserSession
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
    fixed_browser_argv,
)
from lab_generate_skill.adapters.browsergym.worker_protocol import MAX_PACKET
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from browser_worker_fixtures import configuration, LIBS
from browsergym_fixtures import spec, operation, LoopbackAuthority, CHROMIUM
from evidence_control_fixtures import EvidenceFixtureStore
from test_admin_services_native import run_admin_services_probe
from test_admin_description_inputs import (
    FIXTURE,
    public_task,
    reference as native_reference,
)
from test_admin_product_seed import seed
from test_core_contracts import reference
from test_slurm_commands import guard


@pytest.mark.parametrize("execution_mode", ["leaf", "installed"])
def test_actual_admin_setup_publishes_one_authenticated_initial_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    installed_sources: InstalledFixture,
    execution_mode: str,
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv("LD_LIBRARY_PATH", LIBS)
    evidence_root = tmp_path / "browser-evidence"
    evidence_root.mkdir(mode=0o700)
    store = EvidenceFixtureStore(evidence_root)

    def probe(service: AdminServiceSpec, commands: NativeCommands) -> dict[str, Any]:
        native = FIXTURE.read_bytes()
        public = public_task(
            start_url=service.admin_url + json.loads(native)["start_path"]
        )
        binding = load_product_description_inputs(
            native, native_reference(native), public
        )
        product = AdminProductSeed(service, binding.private_spec, seed(), commands)
        initial_product = product.initialize(guard(60))
        original = spec(public.start_url)
        session_spec = BrowserSessionSpec.model_validate(
            {
                **original.model_dump(),
                "task": public,
                "max_events": 4096,
                "scope": original.scope.model_copy(update={"task": public.identity}),
            }
        )
        config = BrowserWorkerConfiguration.model_validate(
            {
                **configuration(storage_installation(installed_sources)).model_dump(),
                "spec": session_spec,
                "initialization": AdminProductInitialization(
                    endpoint=service.admin_url,
                    prepared_ref=reference(content_schema="prepared-task/1"),
                    site_ref=reference(content_schema="site-resource-started/1"),
                ),
            }
        )
        engine: RawBrowserSession
        channel: FramedProcessSession | None = None
        client: SupervisedBrowserSession | None = None
        if execution_mode == "installed":
            channel = FramedProcessSession(
                fixed_browser_argv(config), max_frame_bytes=MAX_PACKET
            )
            client = SupervisedBrowserSession(
                channel, "admin-initialization", config, LoopbackAuthority()
            )
            engine = client
        else:
            engine = BrowserGymEngine(
                session_spec,
                LoopbackAuthority(),
                SystemClock(),
                browser_initializer(config),
            )
        session = EvidenceBrowserSession(engine, store)
        op = operation(session_spec, "admin-browser-initial")
        result: dict[str, Any] = {
            "formal_admission": False,
            "complete_baseline": False,
            "actor_invoked": False,
            "execution_mode": execution_mode,
        }
        primary: BaseException | None = None
        try:
            if channel is not None:
                channel.start(guard(20))
            observed_ref = session.start(op, control=guard(90))
            if client is not None:
                assert (
                    client.last_reply is not None
                    and client.last_reply.owner_guard is not None
                )
                assert client.last_reply.installed_sources is not None
                result["installed_sources"] = (
                    client.last_reply.installed_sources.model_dump(mode="json")
                )
                result["owner_guard"] = client.last_reply.owner_guard.model_dump(
                    mode="json"
                )
            observed = engine.last_readout
            assert observed is not None
            assert observed.observation.sequence == 0 and observed.action is None
            assert observed.events[0].kind == "before_navigation"
            assert not any(
                e.kind in ("before_action", "after_action") for e in observed.events
            )
            assert len(observed.observation.tabs) == 1
            text = observed.observation.text or ""
            assert "Sony Headphones" in text
            assert "Sign in" not in text and "Username" not in text
            _, password = admin_login(guard(5))
            if password in observed.model_dump_json():
                raise RuntimeError("Private login appeared in browser evidence")
            with pytest.raises(InvalidTransition):
                session.start(op, control=guard(5))
            assert product.inspect(guard(30)) == initial_product
            result.update(
                initial_ref=observed_ref.model_dump(mode="json"),
                readout=observed.model_dump(mode="json"),
                product_unchanged=True,
            )
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                session.close(
                    op.cleanup(
                        "admin-browser-close",
                        now=datetime.now(timezone.utc),
                        seconds=20,
                    ),
                    control=guard(20),
                )
                result["browser_state"] = engine.state
                if channel is not None:
                    assert channel.capture.termination is not None
                    assert channel.capture.termination.state == "reaped"
                    assert not channel.capture.termination.cleanup_errors
                    result["original_channel_reaped"] = True
            except BaseException as cleanup:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Admin browser probe and close failed", [primary, cleanup]
                    ) from None
                raise
            finally:
                (
                    Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
                    / "admin-browser-initial.json"
                ).write_text(json.dumps(result, indent=2) + "\n")
        return result

    run_admin_services_probe(probe)
