"""Controlled directions DOM with delayed native signals, never a real Map site."""

from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.sites.map.tasks.overlay_spec import START
from browser_resource_fixtures import ResourceCase
from map_browser_initialization_fixtures import selection, public_task
from map_native_notes_actual import notes_document

DOCUMENT_TARGET = START.split("#", 1)[0]
READY_SCRIPT = """
setTimeout(() => {
  document.getElementById('geo_uri').setAttribute('href', 'geo:40.77,-73.97?z=14');
  document.getElementById('long_link').setAttribute('href', '/#map=14/40.77/-73.97');
  document.getElementById('long_input').value = location.origin + '/#map=14/40.77/-73.97';
}, 250);
"""


def readiness_document() -> tuple[bytes, dict[str, bytes]]:
    document, assets = notes_document()
    assert document.count(b"</html>") == 1
    return (
        document.replace(
            b"</html>",
            (
                '<a id="geo_uri" href="">Native geo</a><input id="long_input" value="">'
                "<script>" + READY_SCRIPT + "</script></html>"
            ).encode(),
        ),
        assets,
    )


def bind_native(c: ResourceCase, endpoint: str) -> None:
    cfg = c.spec.configuration
    updated = BrowserWorkerConfiguration.model_validate(
        cfg.model_copy(
            update={
                "spec": cfg.spec.model_copy(update={"task": public_task(endpoint)}),
                "initialization": selection(endpoint),
            }
        )
    )
    c.spec = BrowserResourceSpec.model_validate(
        c.spec.model_copy(update={"configuration": updated})
    )
