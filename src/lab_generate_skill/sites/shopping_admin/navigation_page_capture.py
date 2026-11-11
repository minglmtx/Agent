"""Selected original h1/login/error probe for the fixed BrowserPageCollector.

The existing browser engine owns durable intent, scope, one-time capture and
post-read cancellation retention. This helper performs only the fixed DOM read.
"""

from typing import Any
from lab_generate_skill.ports.lifecycle import OperationControl
from .evidence_schema import AdminNavigationPage

NAVIGATION_PAGE_PROGRAM = r"""() => {
  const text = document.body ? document.body.innerText : '';
  return {schema_version:'admin-navigation-page/1',url:location.href,
    heading:document.querySelector('h1')?.innerText || '',
    login:!!document.querySelector('form#login-form input[type="password"],body.adminhtml-auth-login input[type="password"]'),
    page_error:location.protocol==='chrome-error:' || /^(404|Page not found|Whoops, our bad)/im.test(document.querySelector('main')?.innerText||text)};
}"""


class AdminNavigationPageCollector:
    def collect(
        self,
        page: Any,
        collector_id: str,
        collector_version: str,
        control: OperationControl,
    ) -> str:
        if (collector_id, collector_version) != ("admin-navigation-page", "1"):
            raise ValueError("Unsupported fixed Admin navigation collector")
        control.checkpoint()
        raw = page.evaluate(NAVIGATION_PAGE_PROGRAM)
        result = AdminNavigationPage.model_validate(raw)
        # Engine retains this obtained fact before checking cancellation again.
        return result.model_dump_json()
