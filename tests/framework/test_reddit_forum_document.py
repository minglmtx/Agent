"""Original directory readiness JS in pinned Chromium, no native site services."""

import os
from pathlib import Path
import pytest
from reddit_forum_document_fixtures import document
from lab_generate_skill.sites.reddit.forum_directory_initial import (
    FORUM_DIRECTORY_READY,
)
from browsergym_fixtures import CHROMIUM


def test_explicit_document_cases_before_browser() -> None:
    assert "/f/EarthPorn" in document("normal") and "/f/EarthPorn" not in document(
        "empty"
    )
    assert "tab--active" not in document("missing-tab")
    assert document("duplicate-tab").count("tab--active") == 2
    assert "columns flow" not in document("missing-list")
    assert "submission[image]" in document("wrong-form")
    assert "display:none" in document("hidden-tab")
    with pytest.raises(ValueError):
        document("unknown")


def test_directory_ready_normal_empty_invalid_and_unchanged_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=CHROMIUM, headless=True)
        try:
            page = browser.new_page()
            page.route(
                "**/*",
                lambda route: route.fulfill(
                    status=200, content_type="text/html", body=document("normal")
                ),
            )
            page.goto(
                "http://127.0.0.1:18080/forums/all", wait_until="domcontentloaded"
            )
            for case in (
                "normal",
                "empty",
                "missing-tab",
                "duplicate-tab",
                "missing-list",
                "wrong-form",
                "hidden-tab",
            ):
                page.set_content(document(case))
                before = page.content()
                assert page.evaluate(FORUM_DIRECTORY_READY) is (
                    case in ("normal", "empty")
                )
                assert page.evaluate(FORUM_DIRECTORY_READY) is (
                    case in ("normal", "empty")
                )
                assert page.content() == before
            for path in ("/submit", "/forums/all?x=1", "/forums/all#x"):
                page.goto(
                    "http://127.0.0.1:18080" + path, wait_until="domcontentloaded"
                )
                assert page.evaluate(FORUM_DIRECTORY_READY) is False
        finally:
            browser.close()
