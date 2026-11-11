"""Current main document only; no fetch, navigation, upload or post effects."""

from typing import Any
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.task_families.document_health import is_error_document
from .evidence_schema import RedditPageHealth

PAGE_HEALTH_PROGRAM = r"""() => {
 const measured=performance.getEntriesByType('navigation')[0]?.responseStatus;
 const status=Number.isInteger(measured)&&measured>=100&&measured<=599?measured:null;
 const path=location.pathname.replace(/\/$/,'');
 const login=path==='/login'||!!document.querySelector('form[action$="/login_check"] input[type="password"]');
 return {schema_version:'reddit-page-health/1',url:location.href,title:document.title,
   http_status:status,status_source:status===null?'unavailable':'navigation_timing',
   login_page:login,error_page:false};
}"""


class RedditPageHealthCollector:
    def collect(
        self,
        page: Any,
        collector_id: str,
        collector_version: str,
        control: OperationControl,
    ) -> str:
        if (collector_id, collector_version) != ("reddit-page-health", "1"):
            raise ValueError("Unsupported fixed Reddit document collector")
        control.checkpoint()
        fact = RedditPageHealth.model_validate(page.evaluate(PAGE_HEALTH_PROGRAM))
        if fact.url != page.url:
            fact = RedditPageHealth.model_validate(
                {
                    **fact.model_dump(),
                    "http_status": None,
                    "status_source": "document_changed",
                }
            )
        result = RedditPageHealth.model_validate(
            {
                **fact.model_dump(),
                "error_page": is_error_document(fact.url, fact.http_status, fact.title),
            }
        )
        control.checkpoint()
        return result.model_dump_json()
