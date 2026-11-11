"""Selected original contracts and independent legacy predicate oracle.

No site, browser, model, source qualification or permission is created here.
Only the selected train contracts are read, after their original pins match.
"""

import ast
from copy import deepcopy
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.plans.admin_native_input import decode_admin_native
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    bind_admin_navigation,
    declare_admin_navigation,
)
from lab_generate_skill.sites.shopping_admin.evidence_schema import AdminNavigationPage
from lab_generate_skill.evaluators.shopping_admin.navigation_predicates import (
    navigation_checks,
)

ROOT = Path("/anvme/workspace/r102bf10-lab-generate-skill")
GROUP = "shopping_admin--navigation--ed0b0c7946c0"
SCOPE = ROOT / "docs/migration/all-task-onboarding-scope-20261102-v1"
ORIGINAL_SHA = "78c81dbbeede135cf92063dd9bdcac497d000b3ccde7cb99ad92bf943acc20c0"
ORIGINAL_PATH = (
    ROOT
    / "docs/migration/task-semantic-review-20261029-v1/sources"
    / ORIGINAL_SHA
    / "admin_pilot.py"
)
NETLOC = "127.0.0.1:18080"


@pytest.fixture(scope="module")
def contracts() -> list[tuple[dict[str, Any], EvidenceRef, PublicTask]]:
    rows = []
    selected = [
        row
        for row in map(json.loads, (SCOPE / "tasks.jsonl").read_text().splitlines())
        if row["effective_batch_id"] == GROUP
    ]
    assert len(selected) == 71
    assert all(
        row["split"] == "train" and row["site"] == "shopping_admin" for row in selected
    )
    assert len({row["source_task_id"] for row in selected}) == 71
    for row in selected:
        pin = row["contract_pin_check"]
        raw = Path(pin["path"]).read_bytes()
        assert (
            hashlib.sha256(raw).hexdigest()
            == pin["expected_sha256"]
            == pin["observed_sha256"]
        )
        reference = EvidenceRef(
            uri="cas://sha256/" + pin["expected_sha256"],
            sha256=pin["expected_sha256"],
            size_bytes=len(raw),
            media_type="application/json",
            content_schema="admin-native-contract/1",
            visibility="private",
            producer="original-admin-navigation",
        )
        native = decode_admin_native(raw, reference)
        public = PublicTask(
            identity=TaskIdentity(
                source_task_id=row["source_task_id"],
                task_id=row["source_task_id"],
                site="shopping_admin",
                split="train",
                family="page_navigation",
                contract_version=1,
            ),
            goal=native["goal"],
            start_url="http://" + NETLOC + "/admin" + native["start_path"],
            allowed_actions=("click", "send_msg_to_user"),
        )
        rows.append((native, reference, public))
    return rows


@pytest.fixture(scope="module")
def original_checks() -> Any:
    raw = ORIGINAL_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL_SHA
    tree = ast.parse(raw)
    functions: list[ast.stmt] = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in ("plain", "page_navigation_checks")
    ]
    assert {node.name for node in functions if isinstance(node, ast.FunctionDef)} == {
        "plain",
        "page_navigation_checks",
    }
    isolated = ast.Module(body=functions, type_ignores=[])
    namespace = {"html": html, "re": re, "urlsplit": urlsplit}
    exec(compile(isolated, str(ORIGINAL_PATH), "exec"), namespace)
    return namespace["page_navigation_checks"]


def test_complete_selected_group_binding_is_pure_and_repeatable(contracts: Any) -> None:
    assert {native["spec"]["initialization"] for native, _, _ in contracts} == {
        "fixed_local_start_not_original_trajectory_start",
        "declared_local_start; original goal unchanged",
    }
    for native, reference, public in contracts:
        before = deepcopy(native)
        value = bind_admin_navigation(native, reference, public)
        assert value == bind_admin_navigation(native, reference, public)
        assert native == before
        assert value.public_task == public
        assert value.private_spec.native_contract_ref == reference
        assert value.private_spec.legacy_runtime_task_id == native["runtime_task_id"]
        assert value.private_spec.store_id == native["scope_id"] == 0
        assert value.private_spec.admission == "unverified"
        assert value.private_spec.initialization == native["spec"]["initialization"]
        assert value.private_spec.start_path == native["spec"]["start_path"]
        assert (
            declare_admin_navigation(native, reference, public.identity, public.goal)
            == value.private_spec
        )
        assert (
            "private_spec" not in PublicTask.model_fields
            and "native_contract_ref" not in PublicTask.model_fields
        )


def test_all71_static_declarations_need_no_allocated_endpoint_or_resources(
    contracts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins
    import os
    import subprocess

    expected = [
        bind_admin_navigation(native, reference, public).private_spec
        for native, reference, public in contracts
    ]
    originals = deepcopy([native for native, _, _ in contracts])

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Static Admin declaration attempted I/O or resource acquisition")

    with monkeypatch.context() as patch:
        for module, name in [
            (builtins, "open"),
            (os, "open"),
            (os, "mkdir"),
            (subprocess, "Popen"),
        ]:
            patch.setattr(module, name, forbidden)
        for _ in range(2):
            actual = [
                declare_admin_navigation(
                    native, reference, public.identity, native["goal"]
                )
                for native, reference, public in contracts
            ]
            assert actual == expected
            assert all(value.admission == "unverified" for value in actual)
    assert [native for native, _, _ in contracts] == originals


def test_all_selected_original_route_and_heading_semantics(
    contracts: Any, original_checks: Any
) -> None:
    for native, reference, public in contracts:
        spec = bind_admin_navigation(native, reference, public).private_spec
        target = "/admin" + native["spec"]["target_path"].rstrip("/")
        headings = [
            native["spec"]["heading"],
            native["spec"]["heading"].swapcase(),
            "<b>" + html.escape(native["spec"]["heading"]) + "</b>",
            "Wrong heading",
            "",
        ]
        routes = [
            target,
            target + "/",
            target + "/index",
            target + "/key/abc123/",
            target + "/index/key/abc123/",
            target + "/edit/id/1/",
            target + "-other",
            target + "/key/",
            public.start_url.split(NETLOC, 1)[1],
        ]
        for route in routes:
            for heading in headings:
                for host, login, error in [
                    (NETLOC, False, False),
                    ("localhost:18080", False, False),
                    (NETLOC, True, False),
                    (NETLOC, False, True),
                ]:
                    page = AdminNavigationPage(
                        url="http://" + host + route,
                        heading=heading,
                        login=login,
                        page_error=error,
                    )
                    expected = original_checks(
                        native["spec"], page.model_dump(), NETLOC
                    )
                    actual = navigation_checks(spec, page, NETLOC)
                    assert actual == expected, (
                        spec.task.source_task_id,
                        page,
                        actual,
                        expected,
                    )
                    if route.endswith("/edit/id/1/") or route.endswith("-other"):
                        assert actual["target_page_url"] is False
        # Original dashboard routes already contain /admin; preserve that prefix.
        if native["spec"]["target_path"].startswith("/admin/"):
            page = AdminNavigationPage(
                url="http://" + NETLOC + native["spec"]["target_path"],
                heading=spec.heading,
                login=False,
                page_error=False,
            )
            assert navigation_checks(spec, page, NETLOC)["target_page_url"] is False


@pytest.mark.parametrize(
    "path,value",
    [
        (("spec", "target_path"), "//foreign/"),
        (("spec", "target_path"), "/one/../two"),
        (("spec", "start_path"), "/x?y=1"),
        (("spec", "target_path"), "/bad route/"),
        (("spec", "heading"), ""),
        (("spec", "heading"), None),
        (("spec", "heading"), 1),
        (("spec", "initialization"), "original_trajectory_start"),
        (("spec", "protocol"), "other"),
        (("spec", "target_path_aliases"), ["/other/"]),
        (("task_revision", "contains_reference_answer"), True),
        (("task_revision", "contains_action_sequence"), True),
        (("task_revision", "previous_revision"), {}),
        (("task_revision", "runtime_goal"), "changed"),
        (("task_revision", "source_task_id"), "other"),
        (("scope_id",), True),
        (("scope_id",), 1),
        (("source_task_id",), "other"),
        (("runtime_task_id",), "other@derived-a"),
        (("runtime_task_id",), "023a2fa510545850eb60@derived-"),
        (("goal",), "changed"),
        (("kind",), "native"),
        (("status",), "admitted"),
        (("not_formal_training_admission",), False),
        (("not_formal_training_admission",), 1),
        (("extra",), 1),
    ],
)
def test_unsupported_native_contract_rejected(
    contracts: Any, path: tuple[str, ...], value: Any
) -> None:
    native, reference, public = contracts[0]
    changed = deepcopy(native)
    node = changed
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises((ValueError, ValidationError)):
        bind_admin_navigation(changed, reference, public)
    with pytest.raises((ValueError, ValidationError)):
        declare_admin_navigation(changed, reference, public.identity, public.goal)


@pytest.mark.parametrize("value", [None, [], False, "", 0, {}])
def test_empty_or_wrong_native_type(contracts: Any, value: Any) -> None:
    _, reference, public = contracts[0]
    with pytest.raises(ValueError):
        bind_admin_navigation(value, reference, public)
    with pytest.raises(ValueError):
        declare_admin_navigation(value, reference, public.identity, public.goal)


@pytest.mark.parametrize(
    "changes",
    [
        {"identity": {"site": "map"}},
        {"identity": {"family": "product_description"}},
        {"identity": {"contract_version": 2}},
        {"goal": "changed"},
        {"start_url": "http://127.0.0.1:18080/admin/wrong/"},
        {"start_url": "https://127.0.0.1:18080/admin/catalog/product/"},
        {"start_url": "http://example.test:18080/admin/catalog/product/"},
        {"start_url": "http://127.0.0.1:18080/admin/catalog/product/?key=other"},
    ],
)
def test_changed_public_contract_rejected(
    contracts: Any, changes: dict[str, Any]
) -> None:
    native, reference, public = contracts[0]
    data = public.model_dump(mode="json")
    for key, value in changes.items():
        if key == "identity":
            data["identity"].update(value)
        else:
            data[key] = value
    changed = PublicTask.model_validate_json(json.dumps(data))
    with pytest.raises(ValueError):
        bind_admin_navigation(native, reference, changed)


def test_invalid_partial_page_evidence_remains_unusable(contracts: Any) -> None:
    native, reference, public = contracts[0]
    spec = bind_admin_navigation(native, reference, public).private_spec
    invalid_pages: list[Any] = [
        {},
        {"url": public.start_url, "login": False, "page_error": False},
        {
            "url": public.start_url,
            "heading": "Dashboard",
            "login": 0,
            "page_error": False,
        },
    ]
    for page in invalid_pages:
        with pytest.raises(ValidationError):
            navigation_checks(spec, page, NETLOC)
