"""One native login, then untouched /submit; no forum, image or post action."""

from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.lifecycle import OperationControl
from .login_navigation import original_login_document
from .forum_directory_initial import FORUM_DIRECTORY_READY
from lab_generate_skill.domain.reddit_image_start import image_start_path

FORM = 'form[action="/login_check"][method="POST"]'
FORM_READY = """() => {
    const fs=Array.from(document.querySelectorAll('form')).filter(f=>{
        const u=new URL(f.action,location.href);
        return u.origin===location.origin && u.pathname==='/login_check' && !u.search && !u.hash && f.method.toLowerCase()==='post';
    });
    if(fs.length!==1)return false;
    const f=fs[0], token=f.querySelectorAll('input[type=hidden][name=_csrf_token]');
    return !!f.getClientRects().length && token.length===1 && !!token[0].value &&
        f.querySelectorAll('input[name=_username][id=login-username]').length===1 &&
        f.querySelectorAll('input[type=password][name=_password][id=login-password]').length===1 &&
        f.querySelectorAll('button[type=submit]').length===1;
}"""
ACCOUNT_READY = """() => {
    const menu=document.querySelectorAll('.site-nav__user-menu');
    if(menu.length!==1)return false;
    const users=menu[0].querySelectorAll('li.dropdown > button.dropdown__toggle > strong.no-mobile');
    const logout=Array.from(menu[0].querySelectorAll('form')).filter(f=>{
        const u=new URL(f.action,location.href);
        return u.origin===location.origin && u.pathname==='/log_out' && f.method.toLowerCase()==='post';
    });
    return users.length===1 && !!users[0].textContent.trim() && logout.length===1;
}"""
ACCOUNT_NAME = "() => document.querySelector('.site-nav__user-menu li.dropdown > button.dropdown__toggle > strong.no-mobile').textContent.trim()"
SUBMISSION_READY = """() => {
    const images=document.querySelectorAll('form[method=post i] input[type=file][name="submission[image]"]');
    if(images.length!==1)return false;
    const f=images[0].form,u=new URL(f.action||location.href,location.href);
    return u.origin===location.origin && u.pathname==='/submit' && !u.search && !u.hash &&
        f.enctype==='multipart/form-data' && f.querySelectorAll('[name="submission[title]"]').length===1 &&
        f.querySelectorAll('[name="submission[forum]"]').length===1 &&
        f.querySelectorAll('input[type=hidden][name="submission[_token]"]').length===1;
}"""


class RedditNativeImageBrowserInitializer:
    def __init__(
        self,
        config: RedditNativeImageInitialization,
        login: Callable[[OperationControl], tuple[str, str]],
    ) -> None:
        self.config = RedditNativeImageInitialization.model_validate_json(
            config.model_dump_json()
        )
        self.login = login
        self.attempted = False

    def setup(self, page: Any, task: PublicTask, control: OperationControl) -> None:
        if self.attempted:
            raise RuntimeError("Reddit browser initialization was already attempted")
        control.checkpoint()
        self.config.check_task(task)
        if task.identity != self.config.task_files.scope.task:
            raise ValueError("Reddit public task differs from its original file plan")
        self.attempted = True
        username, password = self.login(control)
        if username != self.config.native_account_username:
            raise RuntimeError("Reddit login differs from prepared native account")
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

        def navigate(tab: Any, url: str, *, login_document: bool = False) -> None:
            response = tab.goto(url, wait_until="domcontentloaded", timeout=timeout())
            if (
                response is None
                or type(response.status) is not int
                or not 200 <= response.status < 300
                or (
                    not original_login_document(response, tab.url, url)
                    if login_document
                    else tab.url != url
                )
            ):
                raise RuntimeError(
                    "Reddit original login/start document is unhealthy or redirected"
                )

        def account(tab: Any) -> None:
            tab.wait_for_function(ACCOUNT_READY, timeout=timeout())
            if (
                tab.evaluate(ACCOUNT_NAME) != self.config.native_account_username
                or tab.locator(FORM).count()
            ):
                raise RuntimeError(
                    "Reddit browser differs from original native account"
                )

        login_page = page.context.new_page()
        primary: BaseException | None = None
        try:
            navigate(login_page, self.config.endpoint + "login", login_document=True)
            login_page.wait_for_function(FORM_READY, timeout=timeout())
            login_page.locator(FORM + ' input[name="_username"]').fill(
                username, timeout=timeout()
            )
            login_page.locator(FORM + ' input[name="_password"]').fill(
                password, timeout=timeout()
            )
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
                        "Reddit login and private tab cleanup failed",
                        [primary, cleanup],
                    ) from None
                raise
        navigate(page, task.start_url)
        account(page)
        page.wait_for_function(
            (
                FORUM_DIRECTORY_READY
                if image_start_path(task.identity) == "/forums/all"
                else SUBMISSION_READY
            ),
            timeout=timeout(),
        )
        control.checkpoint()
