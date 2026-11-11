"""Project captured public AX/DOM facts with the existing native enhancements."""

from datetime import datetime
from typing import Any
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.observation import Observation, BrowserTab
from .ax_native import with_native_descriptions, with_keyboard_focusable_regions
from .ax_inline import with_rendered_inline_text
from .ax_drag import with_native_drag_regions
from .control_projection import with_public_control_state


def project(
    raw: dict[str, Any], spec: BrowserSessionSpec, sequence: int, captured_at: datetime
) -> Observation:
    from browsergym.utils.obs import flatten_axtree_to_str  # type: ignore[import-untyped]

    tree = with_native_descriptions(raw["axtree_object"])
    tree = with_keyboard_focusable_regions(tree)
    tree = with_native_drag_regions(
        tree, raw.get("dom_object"), raw.get("extra_element_properties", {})
    )
    tree = with_public_control_state(
        tree, raw.get("dom_object"), raw.get("extra_element_properties")
    )
    tree = with_rendered_inline_text(
        tree, raw.get("dom_object"), raw["extra_element_properties"]
    )
    text = flatten_axtree_to_str(
        tree,
        filter_visible_only=False,
        extra_properties=raw["extra_element_properties"],
    )
    urls, titles = raw["open_pages_urls"], raw["open_pages_titles"]
    active = raw["active_page_index"]
    index = int(active.item()) if hasattr(active, "item") else int(active)
    return Observation(
        observation_id=f"observation-{sequence}",
        task=spec.task.identity,
        context_id=spec.scope.context_id,
        attempt_id=spec.scope.attempt_id,
        sequence=sequence,
        captured_at=captured_at,
        tabs=tuple(
            BrowserTab(tab_id=f"tab-{i}", url=url, title=titles[i])
            for i, url in enumerate(urls)
        ),
        active_tab_id=f"tab-{index}",
        state="ready",
        text=text,
        last_action_error=raw["last_action_error"],
    )
