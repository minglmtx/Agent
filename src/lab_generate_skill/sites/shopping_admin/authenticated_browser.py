"""Original private Admin login/routing sequence, without task navigation."""

from typing import Any, Callable
from urllib.parse import urlsplit
from lab_generate_skill.ports.lifecycle import OperationControl


def authenticate_admin(
    page: Any,
    endpoint: str,
    login: Callable[[OperationControl], tuple[str, str]],
    control: OperationControl,
) -> None:
    username, password = login(control)
    origin = urlsplit(endpoint)

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

    # BrowserGym obtains the observation only after this setup returns.
    def timeout() -> float:
        return min(60000, control.checkpoint() * 1000)

    login_page = page.context.new_page()
    primary: BaseException | None = None
    try:
        login_page.goto(endpoint, wait_until="domcontentloaded", timeout=timeout())
        login_page.get_by_label("Username").fill(username, timeout=timeout())
        login_page.get_by_label("Password").fill(password, timeout=timeout())
        login_page.get_by_role("button", name="Sign in").click(timeout=timeout())
        login_page.locator('input[type="password"]').wait_for(
            state="hidden", timeout=timeout()
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
                    "Admin login and page cleanup failed", [primary, cleanup]
                ) from None
            raise
