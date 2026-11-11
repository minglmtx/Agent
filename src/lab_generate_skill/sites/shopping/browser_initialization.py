"""Original customer login and approved account start, before one observation.

No order route, expected date, answer, cookie export or environment credential
fallback. Page handles remain inside the trusted browser worker setup.
"""

from typing import Any, Callable
from urllib.parse import urlsplit
from lab_generate_skill.domain.browser_initialization import ShoppingOrderInitialization
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.lifecycle import OperationControl

FORM_READY = """() => {
    const fields=document.querySelectorAll('form#login-form[action] input[name="form_key"]');
    const entry=document.cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('form_key='));
    return !!(fields.length===1 && fields[0].value && entry &&
        decodeURIComponent(entry.slice(9))===fields[0].value);
}"""


class ShoppingOrderBrowserInitializer:
    def __init__(
        self,
        config: ShoppingOrderInitialization,
        login: Callable[[OperationControl], tuple[str, str]],
    ) -> None:
        self.config = ShoppingOrderInitialization.model_validate(config)
        self.login = login
        self.attempted = False

    def setup(self, page: Any, task: PublicTask, control: OperationControl) -> None:
        if self.attempted:
            raise RuntimeError("Shopping browser initialization was already attempted")
        control.checkpoint()
        self.config.check_task(task)
        self.attempted = True
        username, password = self.login(control)
        origin = urlsplit(self.config.endpoint)

        def local_only(route: Any) -> None:
            url = urlsplit(route.request.url)
            if url.scheme in ("data", "blob", "about") or (url.scheme, url.netloc) == (
                origin.scheme,
                origin.netloc,
            ):
                route.continue_()
            else:
                route.abort()

        page.context.route("**/*", local_only)

        def timeout() -> float:
            return min(60000, control.checkpoint() * 1000)

        login_page = page.context.new_page()
        primary: BaseException | None = None
        try:
            login_page.goto(
                self.config.endpoint + "customer/account/login/",
                wait_until="load",
                timeout=timeout(),
            )
            login_page.wait_for_function(FORM_READY, timeout=min(15000, timeout()))
            login_page.locator(
                'form#login-form[action] input[name="login[username]"]'
            ).fill(username, timeout=timeout())
            login_page.locator(
                'form#login-form[action] input[name="login[password]"]'
            ).fill(password, timeout=timeout())
            login_page.locator('form#login-form[action] button[type="submit"]').click(
                timeout=timeout()
            )
            login_page.wait_for_selector(
                "body.customer-account-index", timeout=timeout()
            )
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                login_page.close()
            except BaseException as cleanup:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Shopping login and page cleanup failed", [primary, cleanup]
                    ) from None
                raise
        page.goto(task.start_url, wait_until="domcontentloaded", timeout=timeout())
        page.wait_for_selector(
            "body.customer-account-index .block-dashboard-info .box-information",
            timeout=timeout(),
        )
        if page.locator('form.form-login input[type="password"]').count():
            raise RuntimeError("Shopping login did not complete")
        actual = urlsplit(page.url)
        if (
            (actual.scheme, actual.netloc, actual.path)
            != (origin.scheme, origin.netloc, "/customer/account/")
            or actual.query
            or actual.fragment
        ):
            raise RuntimeError("Shopping task did not reach original account page")
        info = page.locator(".block-dashboard-info .box-information").inner_text(
            timeout=timeout()
        )
        if username not in [line.strip() for line in info.splitlines()]:
            raise RuntimeError(
                "Shopping account page does not identify the original customer"
            )
        control.checkpoint()
