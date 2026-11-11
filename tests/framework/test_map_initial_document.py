"""Original route document remains fixed while native directions fit their view."""

from typing import Any
import pytest
from lab_generate_skill.sites.map.native_view_rules import original_document
from map_source_inputs import public_task


@pytest.mark.parametrize(
    "fragment",
    ["map=15/40.7695/-73.9738", "map=14/40.7695/-73.9738", "map=14/40.77/-73.97"],
)
def test_declared_document_with_original_auto_pan_and_repeat(fragment: str) -> None:
    task = public_task("http://127.0.0.1:23062/", ("click",))
    actual = task.start_url.split("#")[0] + "#" + fragment
    assert original_document(task, actual)
    assert original_document(task, actual)
    assert task.start_url.endswith("#map=15/40.7695/-73.9738")


@pytest.mark.parametrize(
    "change",
    [
        "origin",
        "scheme",
        "path",
        "route",
        "engine",
        "query",
        "no-query",
        "credentials",
        "control",
        "backslash",
        "oversized",
    ],
)
def test_wrong_document_or_route_never_matches_original(change: str) -> None:
    task = public_task("http://127.0.0.1:23062/", ("click",))
    url = task.start_url
    variants = {
        "origin": url.replace("23062", "23063"),
        "scheme": url.replace("http:", "https:"),
        "path": url.replace("/directions?", "/search?"),
        "route": url.replace("40.7830", "40.7831"),
        "engine": url.replace("fossgis_osrm_car", "fossgis_osrm_bike"),
        "query": url.replace("#", "&foreign=1#"),
        "no-query": "http://127.0.0.1:23062/directions#map=14/40.7695/-73.9738",
        "credentials": url.replace("http://", "http://foreign@"),
        "control": "\n" + url,
        "backslash": url + "\\foreign",
        "oversized": url + "a" * 16384,
    }
    assert original_document(task, variants[change]) is False


@pytest.mark.parametrize(
    "value", [None, "", [], {}, 0, True, float("inf"), "http://[invalid"]
)
def test_empty_invalid_and_wrong_type_url_has_no_document_match(value: Any) -> None:
    task = public_task("http://127.0.0.1:23062/", ("click",))
    assert original_document(task, value) is False


def test_foreign_selected_task_not_accepted_by_document_check() -> None:
    task = public_task("http://127.0.0.1:23062/", ("click",))
    with pytest.raises(ValueError, match="Original selected public Map"):
        original_document(
            task.model_copy(update={"goal": "Other goal"}), task.start_url
        )
