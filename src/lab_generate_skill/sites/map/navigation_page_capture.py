"""Read current document once per capture through the existing browser port."""

import json
from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.task_families.document_health import is_error_document
from .navigation_page_schema import NavigationPageHealth

PAGE = r"""() => {
 const measured=performance.getEntriesByType('navigation')[0]?.responseStatus;
 const status=Number.isInteger(measured)&&measured>=100&&measured<=599?measured:null;
 return {schema_version:'map-navigation-page-health/1',health:{schema_version:'map-page-health/1',
   url:location.href,sampled_url:location.href,title:document.title,
   http_status:status,status_source:status===null?'unavailable':'navigation_timing',
   login_page:false,error_page:false},document_state:document.readyState,
   heading_texts:[...document.querySelectorAll('h1,h2,h3')].map(e=>e.innerText.trim())};
}"""


def navigation_page(page: Any, control: OperationControl) -> NavigationPageHealth:
    control.checkpoint()
    fact = NavigationPageHealth.model_validate_json(
        json.dumps(page.evaluate(PAGE), allow_nan=False)
    )
    current = page.url
    health = fact.health.model_dump()
    if current != fact.health.sampled_url:
        health.update(url=current, http_status=None, status_source="document_changed")
    path = urlsplit(current).path
    health.update(
        login_page=path in ("/login", "/users/sign_in", "/customer/account/login"),
        error_page=is_error_document(current, health["http_status"], health["title"]),
    )
    result = NavigationPageHealth.model_validate(
        {**fact.model_dump(), "health": health}
    )
    control.checkpoint()
    return result
