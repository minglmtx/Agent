"""Production declarations against original18 inputs; no site/model acquisition."""

import hashlib
from typing import Any
import pytest
from lab_generate_skill.bootstrap.shopping_category_navigation import (
    load_category_navigation_inputs,
)
from lab_generate_skill.bootstrap.shopping_category_site_configuration import (
    shopping_category_site_configuration,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.shopping_navigation_origin import ShoppingCategoryOrigin
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA
from site_worker_fixtures import configuration
from test_shopping_category_navigation_input import originals as originals, reference


def declarations(original: Any) -> tuple[Any, ...]:
    raw, _, public = original
    private = load_category_navigation_inputs(raw, reference(raw), public).private_spec
    cfg = configuration()
    scope = StateScope(
        owner=cfg.token.owner,
        task=private.task,
        attempt_id="source-original",
        context_id="source-original-context",
    )
    files = cfg.files.model_copy(
        update={
            "workspace_root": cfg.installation.workspace_root,
            "source_path": cfg.installation.workspace_root + "/" + cfg.files.image.path,
            "image": cfg.files.image.model_copy(update={"sha256": SHOPPING_IMAGE_SHA}),
        }
    )
    return (
        private,
        scope,
        cfg.token,
        files,
        cfg.installation,
        ShoppingCategoryOrigin(endpoint="http://127.0.0.1:18080/"),
    )


def test_original18_declarations_preserve_scope_and_exact_native_private_payload(
    originals: Any,
) -> None:
    observed = set()
    for original in originals:
        args = declarations(original)
        private, scope, token, files, installation, origin = args
        selected = shopping_category_site_configuration(*args)
        assert selected == shopping_category_site_configuration(*args)
        assert selected.schema_version == "site-worker-configuration/9"
        assert selected.site_id == "shopping"
        assert (selected.token, selected.files, selected.installation) == (
            token,
            files,
            installation,
        )
        inputs = selected.shopping_category_inputs
        assert inputs is not None
        assert (inputs.scope, inputs.origin) == (scope, origin)
        assert inputs.native_contract_sha256 == reference(original[0]).sha256
        assert (
            inputs.private_input_sha256
            == hashlib.sha256(
                CategoryNavigationExecutionInput(spec=private)
                .model_dump_json()
                .encode()
            ).hexdigest()
        )
        assert selected.private_evidence is None
        assert selected.admin_navigation_inputs is None
        assert selected.map_inputs is None
        observed.add(scope.task.source_task_id)
    assert len(observed) == 18


@pytest.mark.parametrize(
    "change", ["task", "owner", "image", "workspace", "instance", "provider"]
)
def test_changed_joins_refuse_before_any_acquisition(
    originals: Any, change: str
) -> None:
    args = list(declarations(originals[0]))
    private, scope, token, files, _, _ = args
    error: type[Exception] = OwnershipConflict
    if change == "task":
        args[1] = scope.model_copy(update={"task": declarations(originals[1])[0].task})
    elif change == "owner":
        args[1] = scope.model_copy(
            update={"owner": scope.owner.model_copy(update={"owner_id": "foreign"})}
        )
    elif change == "image":
        args[3] = files.model_copy(
            update={"image": files.image.model_copy(update={"sha256": "0" * 64})}
        )
    elif change == "workspace":
        args[3] = files.model_copy(
            update={
                "workspace_root": "/anvme/workspace/foreign",
                "source_path": "/anvme/workspace/foreign/" + files.image.path,
            }
        )
    elif change == "instance":
        args[2] = token.model_copy(update={"expected_resource_id": "foreign"})
        error = ValueError
    elif change == "provider":
        args[2] = token.model_copy(update={"provider_version": "5"})
        error = ValueError
    with pytest.raises(error):
        shopping_category_site_configuration(*args)


@pytest.mark.parametrize("value", [None, {}, [], "", 0, True])
def test_untyped_or_missing_declarations_are_not_permission(value: Any) -> None:
    with pytest.raises(TypeError, match="Typed original category"):
        shopping_category_site_configuration(value, value, value, value, value, value)
