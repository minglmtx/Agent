"""Group explicit initialization/input and complete prepared-account checks."""

from pathlib import Path
from typing import Any
from types import SimpleNamespace
import pytest
from lab_generate_skill.bootstrap.browser_initialization import browser_initializer
from lab_generate_skill.bootstrap.browser_capture import browser_collector
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.sites.gitlab.browser_initialization import (
    GitlabGroupBrowserInitializer,
    FORM,
)
from lab_generate_skill.sites.gitlab.page_capture import GitlabPageHealthCollector
from lab_generate_skill.sites.gitlab.tasks.group_browser_binding import (
    GroupBrowserChecks,
)
from gitlab_group_fixtures import public_task
from gitlab_group_preparation_fixtures import prepared_case, put
from gitlab_browser_initialization_fixtures import Page
from browser_worker_fixtures import configuration
from test_core_contracts import reference
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


def selection(endpoint: str = "http://127.0.0.1:18080/") -> GitlabGroupInitialization:
    return GitlabGroupInitialization(
        endpoint=endpoint,
        native_account_id=17,
        prepared_ref=reference(content_schema="prepared-task/1"),
        site_ref=reference(content_schema="site-resource-started/1"),
    )


class GroupPage(Page):
    def goto(self, url: str, **kwargs: Any) -> Any:
        super().goto(url, **kwargs)
        return SimpleNamespace(status=200, url=url)


@pytest.mark.parametrize("status", [None, True, "200", 199, 300, 401, 404, 500, 503])
def test_missing_or_unhealthy_group_document_cannot_publish_initial_view(
    status: Any,
) -> None:
    class Unhealthy(GroupPage):
        def goto(self, url: str, **kwargs: Any) -> Any:
            super().goto(url, **kwargs)
            return None if status is None else SimpleNamespace(status=status, url=url)

    page = Unhealthy()
    setup = GitlabGroupBrowserInitializer(
        selection(), lambda control: ("native-user", "private-password")
    )
    with pytest.raises(RuntimeError, match="missing or unhealthy"):
        setup.setup(page, public_task(), guard())
    assert page.login.calls[-1] == "close" and page.calls == [
        "route",
        "new_page",
        "goto",
    ]
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, public_task(), guard())


def test_group_fixed_dispatch_and_original_public_form_no_task_prefill() -> None:
    task = public_task()
    base = configuration()
    spec = BrowserSessionSpec.model_validate(
        {
            **base.spec.model_dump(),
            "task": task,
            "scope": base.spec.scope.model_copy(update={"task": task.identity}),
        }
    )
    cfg = BrowserWorkerConfiguration.model_validate(
        {**base.model_dump(), "spec": spec, "initialization": selection()}
    )
    assert BrowserWorkerConfiguration.model_validate_json(cfg.model_dump_json()) == cfg
    assert isinstance(browser_initializer(cfg), GitlabGroupBrowserInitializer)
    assert isinstance(browser_collector(cfg), GitlabPageHealthCollector)
    page = GroupPage()
    setup = GitlabGroupBrowserInitializer(
        selection(), lambda control: ("native-user", "private-password")
    )
    setup.setup(page, task, guard())
    assert page.url == task.start_url and page.login.url.endswith("/users/sign_in")
    assert page.calls == ["route", "new_page", "goto", "account_ready", "account_id"]
    assert page.login.calls.count("fill") == 2 and page.login.calls[-1] == "close"
    assert page.selectors == [FORM]
    assert "fill" not in page.calls and "click" not in page.calls
    assert all(s.startswith(FORM) for s in page.login.selectors)
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, task, guard())


@pytest.mark.parametrize(
    "account", [0, -1, 9223372036854775808, True, None, "17", [], {}]
)
def test_group_account_empty_wrong_type_and_extremes_refused(account: Any) -> None:
    with pytest.raises(ValueError):
        GitlabGroupInitialization.model_validate(
            {**selection().model_dump(), "native_account_id": account}
        )


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/groups/new",
        "groups/new?hidden=1",
        "groups/new#x",
        "groups/new/",
        "-/profile/keys",
    ],
)
def test_wrong_group_public_start_rejected_before_credentials(suffix: str) -> None:
    task = public_task().model_copy(
        update={"start_url": "http://127.0.0.1:18080/" + suffix}
    )
    page = GroupPage()
    setup = GitlabGroupBrowserInitializer(
        selection(), lambda control: pytest.fail("No credentials for invalid task")
    )
    with pytest.raises(ValueError):
        setup.setup(page, task, guard())
    assert not page.calls and not setup.attempted


@pytest.mark.parametrize("port", [1024, 65535])
def test_group_port_boundaries_retain_form_start(port: int) -> None:
    init = selection(f"http://127.0.0.1:{port}/")
    init.check_task(
        public_task().model_copy(update={"start_url": init.endpoint + "groups/new"})
    )


@pytest.mark.parametrize("where", ["login", "public"])
def test_group_account_mismatch_closes_private_login_tab(where: str) -> None:
    page = GroupPage()
    (page.login if where == "login" else page).account_id = 18
    setup = GitlabGroupBrowserInitializer(
        selection(), lambda control: ("native-user", "private-password")
    )
    with pytest.raises(RuntimeError, match="original native account"):
        setup.setup(page, public_task(), guard())
    assert page.login.calls[-1] == "close"


def test_group_cancel_before_effects_and_partial_close_errors() -> None:
    page = GroupPage()
    setup = GitlabGroupBrowserInitializer(
        selection(), lambda control: pytest.fail("Cancelled before credential read")
    )
    with pytest.raises(OperationStopped):
        setup.setup(page, public_task(), guard(-1))
    assert not page.calls and not setup.attempted
    setup = GitlabGroupBrowserInitializer(
        selection(), lambda control: ("native-user", "private-password")
    )
    page.login.failure = "click"
    page.login.close_error = True
    with pytest.raises(BaseExceptionGroup) as caught:
        setup.setup(page, public_task(), guard())
    assert [type(e) for e in caught.value.exceptions] == [RuntimeError, OSError]
    assert page.login.calls[-1] == "close"


@pytest.mark.parametrize(
    "fault",
    ["none", "account", "configuration", "profile", "request", "guard", "instance"],
)
def test_group_prepared_account_and_original_context_are_recomputed_readonly(
    tmp_path: Path, node_path: Path, fault: str
) -> None:
    with prepared_case(tmp_path, node_path) as c:
        request = c.inputs.request
        result_ref = put(c.store, c.inputs.result)
        context = c.native.artifacts.context
        selected = GitlabGroupInitialization(
            endpoint=context.instance.endpoint,
            native_account_id=1,
            prepared_ref=reference(content_schema="prepared-task/1"),
            site_ref=reference(content_schema="site-resource-started/1"),
        )
        cfg, instance, owner_guard = (
            c.configuration,
            context.instance,
            context.owner_guard,
        )
        if fault == "account":
            selected = selected.model_copy(update={"native_account_id": 2})
        elif fault == "configuration":
            cfg = cfg.model_copy(update={"apptainer": "/usr/bin/foreign"})
        elif fault == "profile":
            from lab_generate_skill.domain.native_private_json import (
                GITLAB_PRIVATE_JSON,
            )

            assert cfg.private_evidence is not None
            cfg = cfg.model_copy(
                update={
                    "private_evidence": cfg.private_evidence.model_copy(
                        update={"profile": GITLAB_PRIVATE_JSON}
                    )
                }
            )
        elif fault == "request":
            request = request.model_copy(
                update={
                    "operation": request.operation.model_copy(
                        update={"operation_id": "foreign"}
                    )
                }
            )
        elif fault == "guard":
            owner_guard = owner_guard.model_copy(
                update={
                    "controller": owner_guard.controller.model_copy(
                        update={"start_ticks": 2}
                    )
                }
            )
        elif fault == "instance":
            instance = instance.model_copy(
                update={"endpoint": "http://127.0.0.1:19999/"}
            )
        calls = len(c.native.sql.calls)
        if fault == "none":
            GroupBrowserChecks(c.store, load_group_capture).check_native_account(
                result_ref, request, selected, cfg, instance, owner_guard, guard()
            )
        else:
            with pytest.raises((ValueError, OwnershipConflict)):
                GroupBrowserChecks(c.store, load_group_capture).check_native_account(
                    result_ref, request, selected, cfg, instance, owner_guard, guard()
                )
        assert len(c.native.sql.calls) == calls
