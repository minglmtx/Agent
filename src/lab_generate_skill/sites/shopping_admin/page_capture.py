"""Exact legacy login/error predicates, without its unrelated UI probes."""

from typing import Any
from lab_generate_skill.ports.lifecycle import OperationControl
from .evidence_schema import AdminPageHealth

PAGE_HEALTH_PROGRAM = r"""() => {
  const text = document.body ? document.body.innerText : '';
  return {schema_version:'admin-page-health/1',url:location.href,
    login:!!document.querySelector('form#login-form input[type="password"],body.adminhtml-auth-login input[type="password"]'),
    page_error:location.protocol==='chrome-error:' || /^(404|Page not found|Whoops, our bad)/im.test(document.querySelector('main')?.innerText||text)};
}"""


class AdminPageHealthCollector:
    def collect(
        self,
        page: Any,
        collector_id: str,
        collector_version: str,
        control: OperationControl,
    ) -> str:
        if (collector_id, collector_version) != ("admin-page-health", "1"):
            raise ValueError("Unsupported fixed Admin page collector")
        control.checkpoint()
        raw = page.evaluate(PAGE_HEALTH_PROGRAM)
        result = AdminPageHealth.model_validate(raw)
        # The engine retains this obtained fact before its post-read checkpoint.
        return result.model_dump_json()
