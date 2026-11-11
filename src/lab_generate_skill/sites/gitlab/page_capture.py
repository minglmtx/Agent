"""Current native document/account only; never navigate, fetch or infer status."""

from typing import Any
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.task_families.document_health import is_error_document
from .evidence_schema import GitlabPageHealth as GitlabPageHealth

PAGE_HEALTH_PROGRAM = r"""() => {
 const measured=performance.getEntriesByType('navigation')[0]?.responseStatus;
 const status=Number.isInteger(measured)&&measured>=100&&measured<=599?measured:null;
 const account=window.gon?.current_user_id;
 const login=!!document.querySelector('form[data-testid="sign-in-form"] input[type="password"]')||
   ['/users/sign_in','/login'].includes(location.pathname.replace(/\/$/,''));
 return {schema_version:'gitlab-page-health/1',url:location.href,title:document.title,
   http_status:status,status_source:status===null?'unavailable':'navigation_timing',
   login_page:login,error_page:false,
   account_id:!login&&Number.isInteger(account)&&account>0?account:null};
}"""


class GitlabPageHealthCollector:
    def collect(
        self,
        page: Any,
        collector_id: str,
        collector_version: str,
        control: OperationControl,
    ) -> str:
        if (collector_id, collector_version) != ("gitlab-page-health", "1"):
            raise ValueError("Unsupported fixed GitLab document collector")
        control.checkpoint()
        fact = GitlabPageHealth.model_validate(page.evaluate(PAGE_HEALTH_PROGRAM))
        if fact.url != page.url:
            fact = GitlabPageHealth.model_validate(
                {
                    **fact.model_dump(),
                    "http_status": None,
                    "status_source": "document_changed",
                    "account_id": None,
                }
            )
        result = GitlabPageHealth.model_validate(
            {
                **fact.model_dump(),
                "error_page": is_error_document(fact.url, fact.http_status, fact.title),
            }
        )
        control.checkpoint()
        return result.model_dump_json()
