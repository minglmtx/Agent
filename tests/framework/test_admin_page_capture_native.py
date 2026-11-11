"""Actual Chromium DOM semantics; controlled local pages, no website or model."""

import os
from pathlib import Path
import pytest
from lab_generate_skill.sites.shopping_admin.page_capture import (
    AdminPageHealthCollector,
)
from lab_generate_skill.sites.shopping_admin.evidence_schema import AdminPageHealth
from browsergym_fixtures import CHROMIUM
from test_slurm_commands import guard


def test_original_login_and_page_error_predicates_in_chromium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )
    cases = [
        ("<main>Product ready</main>", False, False),
        ('<form id="login-form"><input type="password"></form>', True, False),
        (
            '<body class="adminhtml-auth-login"><input type="password"></body>',
            True,
            False,
        ),
        ('<input type="password">', False, False),
        ("<main>404 page</main>", False, True),
        ("<main>Header<br>page NOT found</main>", False, True),
        ("<main>Whoops, our bad</main>", False, True),
        ("<main>Product 404 marker</main>", False, False),
        ("<div>404</div><main>Product ready</main>", False, False),
        ("<div>404</div><main></main>", False, True),
    ]
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=CHROMIUM, headless=True)
        try:
            page = browser.new_page()
            collector = AdminPageHealthCollector()
            for html, login, page_error in cases:
                page.set_content(html)
                facts = AdminPageHealth.model_validate_json(
                    collector.collect(page, "admin-page-health", "1", guard(10))
                )
                assert (facts.login, facts.page_error) == (login, page_error), html
                assert facts.url == page.url
        finally:
            browser.close()
