"""Current native document HTTP/DOM facts; no reload, request or guessed status."""

from typing import Any
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.task_families.document_health import is_error_document
from .evidence_schema import ShoppingPageHealth as ShoppingPageHealth

PAGE_HEALTH_PROGRAM = r"""() => {
 const measured=performance.getEntriesByType('navigation')[0]?.responseStatus;
 const status=Number.isInteger(measured)&&measured>=100&&measured<=599?measured:null;
 return {schema_version:'shopping-page-health/1',url:location.href,title:document.title,
   http_status:status,status_source:status===null?'unavailable':'navigation_timing',
   login_page:!!document.querySelector('form.form-login input[type="password"],body.customer-account-login input[type="password"]')||location.pathname.replace(/\/$/,'')==='/customer/account/login',
   error_page:false};
}"""


class ShoppingPageHealthCollector:
    def collect(
        self,
        page: Any,
        collector_id: str,
        collector_version: str,
        control: OperationControl,
    ) -> str:
        if (collector_id, collector_version) != ("shopping-page-health", "1"):
            raise ValueError("Unsupported fixed Shopping document collector")
        control.checkpoint()
        raw = page.evaluate(PAGE_HEALTH_PROGRAM)
        fact = ShoppingPageHealth.model_validate(raw)
        if fact.url != page.url:
            fact = ShoppingPageHealth.model_validate(
                {
                    **fact.model_dump(),
                    "http_status": None,
                    "status_source": "document_changed",
                }
            )
        return ShoppingPageHealth.model_validate(
            {
                **fact.model_dump(),
                "error_page": is_error_document(fact.url, fact.http_status, fact.title),
            }
        ).model_dump_json()
