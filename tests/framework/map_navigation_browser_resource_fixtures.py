"""One shared explicit synthetic browser backend for initial and source-entry tests."""

from dataclasses import dataclass
from types import SimpleNamespace
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.worker_service import BrowserService
from lab_generate_skill.bootstrap.browser_engine import build_browser_engine
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.lifecycle import AllocationToken
from evidence_control_fixtures import EvidenceFixtureStore
from browser_resource_fixtures import resource_case, ResourceCase, ResourceChannel
from browser_process_fixtures import case as synthetic_browser
from browser_worker_fixtures import sources
from generator_worker_fixtures import unit_guard
from browsergym_fixtures import LoopbackAuthority
from map_navigation_browser_fixtures import Page, Clock


@dataclass
class NavigationBrowserDouble:
    resource: ResourceCase
    engines: list[BrowserGymEngine]
    pages: list[Page]
    calls: list[str]


def navigation_browser_resource(
    root: Path,
    patch: pytest.MonkeyPatch,
    *,
    configuration: BrowserWorkerConfiguration,
    store: EvidenceFixtureStore,
    declared_token: AllocationToken,
    site: SiteResourceSpec,
    public_text: str | None = None,
    step_effect: Callable[[Page, str], None] | None = None,
    page_type: type[Page] = Page,
) -> NavigationBrowserDouble:
    b = resource_case(
        root,
        patch,
        config=configuration,
        store=store,
        declared_token=declared_token,
    )
    b.spec = BrowserResourceSpec.model_validate(
        b.spec.model_copy(
            update={
                "slurm": b.spec.slurm.model_copy(
                    update={
                        "execution": site.slurm.execution,
                        "parent": site.slurm.parent,
                    }
                )
            }
        )
    )
    _, _, calls = synthetic_browser(patch)
    from importlib import import_module

    module = import_module("browsergym.core.env")
    original_init = module.BrowserEnv.__init__
    original_step = module.BrowserEnv.step
    original_reset = module.BrowserEnv.reset
    clock = Clock()
    pages: list[Page] = []
    engines: list[BrowserGymEngine] = []

    def navigation_page(context: object) -> Page:
        page = page_type(clock)
        setattr(page, "context", context)
        return page

    def initialize_env(env: Any, **kwargs: Any) -> None:
        original_init(env, **kwargs)
        env.page = navigation_page(env.page.context)
        pages.append(env.page)

    def with_geometry(raw: dict[str, Any]) -> dict[str, Any]:
        # Explicit synthetic RGB dimensions/unknown element geometry. No real browser claim.
        return {
            **raw,
            "screenshot": SimpleNamespace(shape=(720, 1280, 3)),
            "extra_element_properties": {},
        }

    def reset(env: Any, *, seed: int) -> Any:
        raw, info = original_reset(env, seed=seed)
        return with_geometry(raw), info

    def step(env: Any, payload: str) -> Any:
        returned = original_step(env, payload)
        if step_effect is not None:
            step_effect(env.page, payload)
        raw, reward, terminated, truncated, info = returned
        return with_geometry(raw), reward, terminated, truncated, info

    if public_text is not None:
        import lab_generate_skill.adapters.browsergym.engine as engine_module
        from lab_generate_skill.domain.browser_session import BrowserSessionSpec
        from lab_generate_skill.domain.observation import Observation
        from datetime import datetime

        # Wrap the explicit synthetic projector installed above; the real
        # AX projector correctly rejects this fixture's empty raw dict.
        original_project = cast(
            Callable[[dict[str, Any], BrowserSessionSpec, int, datetime], Observation],
            getattr(engine_module, "project"),
        )

        def project(
            raw: dict[str, Any],
            spec: BrowserSessionSpec,
            sequence: int,
            captured_at: datetime,
        ) -> Observation:
            value = original_project(raw, spec, sequence, captured_at)
            return value.model_copy(
                update={
                    "text": public_text,
                    "tabs": tuple(
                        t.model_copy(update={"url": pages[0].url}) for t in value.tabs
                    ),
                }
            )

        patch.setattr(engine_module, "project", project)

    def factory(config: BrowserWorkerConfiguration) -> BrowserGymEngine:
        engine = build_browser_engine(
            config, LoopbackAuthority(), clock, worker_guard=None
        )
        engines.append(engine)
        return engine

    def channel(*args: Any, **kwargs: Any) -> ResourceChannel:
        result = ResourceChannel(b)
        result.service = BrowserService(factory, sources, unit_guard)
        b.channels.append(result)
        return result

    patch.setattr(module.BrowserEnv, "__init__", initialize_env)
    patch.setattr(module.BrowserEnv, "reset", reset)
    patch.setattr(module.BrowserEnv, "step", step)
    patch.setattr(
        "lab_generate_skill.adapters.browsergym.resource.FramedProcessSession",
        channel,
    )
    return NavigationBrowserDouble(b, engines, pages, calls)
