"""One native login before observation; no private SSH route or key action."""

from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
    GitlabGroupInitialization,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.lifecycle import OperationControl

FORM = 'form[data-testid="sign-in-form"][method="post"]'
FORM_READY = """() => {
    const forms=document.querySelectorAll('form[data-testid="sign-in-form"][method="post"]');
    if(forms.length!==1) return false;
    const f=forms[0], action=new URL(f.action,location.href);
    const token=f.querySelectorAll('input[name="authenticity_token"]');
    return action.origin===location.origin && action.pathname==='/users/sign_in' &&
        !action.search && !action.hash && !!f.getClientRects().length &&
        token.length===1 && !!token[0].value &&
        f.querySelectorAll('input[name="user[login]"]').length===1 &&
        f.querySelectorAll('input[name="user[password]"][type="password"]').length===1 &&
        f.querySelectorAll('button[type="submit"]').length===1;
}"""
ACCOUNT_READY = "() => Number.isInteger(window.gon?.current_user_id) && window.gon.current_user_id > 0"


class _GitlabAccountBrowserInitializer:
    def __init__(
        self,
        config: GitlabSshKeyInitialization | GitlabGroupInitialization,
        login: Callable[[OperationControl], tuple[str, str]],
        public_document: Callable[[Any, PublicTask], None],
    ) -> None:
        self.config = config
        self.login = login
        self.public_document = public_document
        self.attempted = False

    def setup(self, page: Any, task: PublicTask, control: OperationControl) -> None:
        if self.attempted:
            raise RuntimeError("GitLab browser initialization was already attempted")
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

        def account(tab: Any) -> None:
            tab.wait_for_function(ACCOUNT_READY, timeout=timeout())
            actual = tab.evaluate("() => window.gon.current_user_id")
            if (
                type(actual) is not int
                or actual != self.config.native_account_id
                or tab.locator(FORM).count()
            ):
                raise RuntimeError(
                    "GitLab browser differs from original native account"
                )

        login_page = page.context.new_page()
        primary: BaseException | None = None
        try:
            login_page.goto(
                self.config.endpoint + "users/sign_in",
                wait_until="domcontentloaded",
                timeout=timeout(),
            )
            login_page.wait_for_function(FORM_READY, timeout=timeout())
            login_page.locator(FORM + ' input[name="user[login]"]').fill(
                username, timeout=timeout()
            )
            login_page.locator(
                FORM + ' input[name="user[password]"][type="password"]'
            ).fill(password, timeout=timeout())
            login_page.locator(FORM + ' button[type="submit"]').click(timeout=timeout())
            account(login_page)
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                login_page.close()
            except BaseException as cleanup:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "GitLab login and page cleanup failed", [primary, cleanup]
                    ) from None
                raise
        document = page.goto(
            task.start_url, wait_until="domcontentloaded", timeout=timeout()
        )
        self.public_document(document, task)
        account(page)
        if page.url != task.start_url:
            raise RuntimeError("GitLab task did not reach original public start")
        control.checkpoint()


class GitlabSshKeyBrowserInitializer(_GitlabAccountBrowserInitializer):
    def __init__(
        self,
        config: GitlabSshKeyInitialization,
        login: Callable[[OperationControl], tuple[str, str]],
    ) -> None:
        super().__init__(
            GitlabSshKeyInitialization.model_validate(config),
            login,
            unchanged_ssh_document,
        )


class GitlabGroupBrowserInitializer(_GitlabAccountBrowserInitializer):
    def __init__(
        self,
        config: GitlabGroupInitialization,
        login: Callable[[OperationControl], tuple[str, str]],
    ) -> None:
        super().__init__(
            GitlabGroupInitialization.model_validate(config),
            login,
            require_group_document,
        )


def unchanged_ssh_document(response: Any, task: PublicTask) -> None:
    """Retain accepted SSH initialization behavior; its health oracle is separate."""


def require_group_document(response: Any, task: PublicTask) -> None:
    """Use the actual navigation reply, never another HTTP request or observation."""
    if (
        response is None
        or type(response.status) is not int
        or not 200 <= response.status < 300
        or response.url != task.start_url
    ):
        raise RuntimeError("Original Group public document is missing or unhealthy")
