"""One passive terminal read after the original process publication, before close.

Original runner login/error predicates are preserved. Navigation Timing is
native current-document evidence; unavailable status remains unknown. No HTTP,
reload, extra Observation, stored-response inference or success assumption.
"""

from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.task_families.document_health import is_error_document
from .browser_collection import MapBrowserCollection
from .page_health import MapPageHealth

PAGE_HEALTH_PROGRAM = r"""() => {
 const measured=performance.getEntriesByType('navigation')[0]?.responseStatus;
 const status=Number.isInteger(measured)&&measured>=100&&measured<=599?measured:null;
 return {url:location.href,sampled_url:location.href,title:document.title,
   http_status:status,status_source:status===null?'unavailable':'navigation_timing',
   login_page:false,error_page:false};
}"""


class MapPageHealthCapture:
    def __init__(self, process: MapBrowserCollection) -> None:
        self.process = process
        self.attempted = False
        self.sample: Any = None
        self.result: MapPageHealth | None = None

    def collect(self, page: Any, version: str, control: OperationControl) -> str:
        p = self.process
        p._owner()
        if version != "1" or page is not p.page:
            raise OwnershipConflict(
                "Original Map page and fixed health version required"
            )
        if self.attempted or p.state != "published" or p.publication is None:
            raise InvalidTransition(
                "Health requires original terminal publication, once"
            )
        control.checkpoint()
        self.attempted = True
        self.sample = page.evaluate(PAGE_HEALTH_PROGRAM)
        fact = MapPageHealth.model_validate(self.sample)
        current = page.url
        if current != fact.sampled_url:
            fact = MapPageHealth.model_validate(
                {
                    **fact.model_dump(),
                    "url": current,
                    "http_status": None,
                    "status_source": "document_changed",
                }
            )
        path = urlsplit(fact.url).path
        self.result = MapPageHealth.model_validate(
            {
                **fact.model_dump(),
                "login_page": any(
                    x in path for x in ("/users/sign_in", "/customer/account/login")
                )
                or path == "/login",
                "error_page": is_error_document(fact.url, fact.http_status, fact.title),
            }
        )
        control.checkpoint()
        return self.result.model_dump_json()
