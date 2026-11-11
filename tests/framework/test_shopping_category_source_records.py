"""All18 source declarations over actual CAS/caller and synthetic site metadata."""

from dataclasses import replace
import hashlib
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.adapters.sites.shopping_category_source_authority import (
    CategoryNavigationSourceSiteAuthority,
)
from lab_generate_skill.bootstrap.shopping_category_source_records import (
    CategoryNavigationSourceRecordPolicy,
)
from lab_generate_skill.bootstrap.shopping_category_site_configuration import (
    shopping_category_site_configuration,
)
from lab_generate_skill.bootstrap.shopping_category_source_measurement import (
    category_navigation_measurement_binding,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceNotFound
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.shopping_navigation_origin import (
    ShoppingCategoryOrigin,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA
from test_shopping_category_navigation_input import originals as originals, reference
from site_instance_fixtures import node_path as node_path
from site_resource_fixtures import resource_case, Case
from site_worker_fixtures import configuration, Instance
from test_linux_cgroups import actual_slurm_execution
from test_slurm_commands import guard
from retrieval_fixtures import reference as synthetic_ref


def source_case(
    root: Path, node: Path, patch: pytest.MonkeyPatch, public: Any, raw: bytes
) -> tuple[OriginalSourceQualificationOwner, Case]:
    execution, _ = actual_slurm_execution()
    controller = observe_current_cgroup(
        execution, current_process_identity(), guard(30)
    ).membership
    cfg = configuration(job_id=execution.job_id)
    scope = StateScope(
        owner=cfg.token.owner,
        task=public.identity,
        attempt_id="source-category",
        context_id="source-category-context",
    )
    private = CategoryNavigationSourceRecordPolicy(raw, reference(raw), public).private
    files = cfg.files.model_copy(
        update={
            "workspace_root": cfg.installation.workspace_root,
            "source_path": cfg.installation.workspace_root + "/" + cfg.files.image.path,
            "node_root": str(node / "fresh-source"),
            "image": cfg.files.image.model_copy(update={"sha256": SHOPPING_IMAGE_SHA}),
        }
    )
    cfg = shopping_category_site_configuration(
        private,
        scope,
        cfg.token,
        files,
        cfg.installation,
        ShoppingCategoryOrigin(endpoint="http://127.0.0.1:12001/"),
    )
    c = resource_case(root, patch, config=cfg)
    c.spec = SiteResourceSpec.model_validate(
        c.spec.model_copy(
            update={
                "slurm": c.spec.slurm.model_copy(
                    update={"execution": execution, "parent": controller}
                )
            }
        )
    )
    return OriginalSourceQualificationOwner(scope, execution, controller, c.evidence), c


class NoRead:
    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        raise AssertionError("Pure measurement declaration must not read or acquire")


def test_all18_source_definitions_and_measurements_keep_original_start_and_public_scope(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, originals: Any
) -> None:
    owner, c = source_case(
        tmp_path, node_path, monkeypatch, originals[0][2], originals[0][0]
    )
    site = Instance(c.spec.configuration).start(guard())
    seen = set()
    for raw, native, public in originals:
        ref = reference(raw)
        assert (
            c.evidence.put(
                raw,
                EvidenceMetadata.model_validate(
                    ref.model_dump(
                        include={
                            "media_type",
                            "content_schema",
                            "visibility",
                            "producer",
                        }
                    )
                ),
            )
            == ref
        )
        policy = CategoryNavigationSourceRecordPolicy(raw, ref, public)
        current = OriginalSourceQualificationOwner(
            owner.scope.model_copy(update={"task": public.identity}),
            owner.execution,
            owner.controller,
            c.evidence,
        )
        cfg = c.spec.configuration
        selected = cfg.shopping_category_inputs
        assert selected is not None
        cfg = SiteWorkerConfiguration.model_validate(
            cfg.model_copy(
                update={
                    "shopping_category_inputs": selected.model_copy(
                        update={
                            "scope": current.scope,
                            "native_contract_sha256": ref.sha256,
                            "private_input_sha256": hashlib.sha256(
                                CategoryNavigationExecutionInput(spec=policy.private)
                                .model_dump_json()
                                .encode()
                            ).hexdigest(),
                        }
                    )
                }
            )
        )
        definition = policy.definition(current, cfg, site, guard())
        assert policy.definition(current, cfg, site, guard()) == definition
        assert definition.public.goal == native["goal"]
        assert definition.public.start_url == site.endpoint[:-1] + native["start_path"]
        assert definition.spec.task == public.identity
        assert (
            CategoryNavigationExecutionInput.model_validate_json(
                definition.private_input
            ).spec
            == policy.private
        )
        binding = category_navigation_measurement_binding(
            policy.private,
            definition.public,
            site.endpoint,
            synthetic_ref({}, "prepared-task/1"),
            synthetic_ref({}, "site-resource-started/1"),
            NoRead(),
        )
        assert isinstance(binding.initialization, ShoppingCategoryInitialization)
        assert binding.initialization.native_contract_sha256 == ref.sha256
        assert binding.collector == ("shopping-category-navigation-page", "1")
        for value in (definition.public.model_dump_json(),):
            assert "completion" not in value and "admission_result" not in value
        seen.add(public.identity.source_task_id)
    assert len(seen) == 18 and c.channels == []


@pytest.mark.parametrize(
    "fault", ["task", "owner", "site", "image", "files", "origin", "missing"]
)
def test_source_definition_refuses_foreign_inputs_before_effects(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    raw, _, public = originals[0]
    owner, c = source_case(tmp_path, node_path, monkeypatch, public, raw)
    policy = CategoryNavigationSourceRecordPolicy(raw, reference(raw), public)
    cfg = c.spec.configuration
    site = Instance(cfg).start(guard())
    if fault != "missing":
        ref = policy.reference
        c.evidence.put(
            raw,
            EvidenceMetadata.model_validate(
                ref.model_dump(
                    include={"media_type", "content_schema", "visibility", "producer"}
                )
            ),
        )
    if fault == "task":
        owner.scope = owner.scope.model_copy(update={"task": originals[1][2].identity})
    elif fault == "owner":
        owner.scope = owner.scope.model_copy(
            update={
                "owner": owner.scope.owner.model_copy(update={"owner_id": "foreign"})
            }
        )
    elif fault == "site":
        cfg = cfg.model_copy(update={"site_id": "shopping_admin"})
    elif fault == "image":
        cfg = cfg.model_copy(
            update={
                "files": cfg.files.model_copy(
                    update={
                        "image": cfg.files.image.model_copy(update={"sha256": "0" * 64})
                    }
                )
            }
        )
    elif fault == "files":
        site = site.model_copy(
            update={
                "files": site.files.model_copy(
                    update={"node_root": str(node_path / "foreign")}
                )
            }
        )
    elif fault == "origin":
        site = site.model_copy(update={"endpoint": site.endpoint + "admin"})
    expected: Any = (
        ValueError if fault == "site" else (OwnershipConflict, EvidenceNotFound)
    )
    with pytest.raises(expected):
        policy.definition(owner, cfg, site, guard())
    assert c.channels == []


@pytest.mark.parametrize(
    "fault",
    ["goal", "path", "query", "fragment", "origin", "prepared", "site", "checks"],
)
def test_measurement_binding_refuses_changed_original_public_or_capture_policy(
    originals: Any, fault: str
) -> None:
    raw, _, public = originals[0]
    private = CategoryNavigationSourceRecordPolicy(raw, reference(raw), public).private
    prepared, site = synthetic_ref({}, "prepared-task/1"), synthetic_ref(
        {}, "site-resource-started/1"
    )
    if fault == "goal":
        public = public.model_copy(update={"goal": "foreign"})
    elif fault in {"path", "query", "fragment"}:
        public = public.model_copy(
            update={
                "start_url": public.start_url
                + {"path": "/other", "query": "&x=1", "fragment": "#other"}[fault]
            }
        )
    if fault == "prepared":
        prepared = site
    elif fault == "site":
        site = prepared
    with pytest.raises((ValueError, TypeError, OwnershipConflict)):
        binding = category_navigation_measurement_binding(
            private,
            public,
            (
                "http://127.0.0.1:19000/"
                if fault == "origin"
                else "http://127.0.0.1:18080/"
            ),
            prepared,
            site,
            NoRead(),
        )
        if fault == "checks":
            replace(binding, initial_checks=None)  # type: ignore[arg-type]


def test_actual_source_rights_are_once_only_and_do_not_grant_native_or_actor_work(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
) -> None:
    owner, c = source_case(
        tmp_path, node_path, monkeypatch, originals[0][2], originals[0][0]
    )
    authority = CategoryNavigationSourceSiteAuthority(owner, c.spec, c.op)
    control = c.controls.bind(c.op)
    authority.authorize_spawn(c.spec, c.op, control)
    with pytest.raises(OwnershipConflict):
        authority.authorize_spawn(c.spec, c.op, control)
    authority.verify(c.spec.configuration, "configure", c.op, control)
    with pytest.raises(OwnershipConflict):
        authority.verify(c.spec.configuration, "configure", c.op, control)
    owner.seal(c.op, control)
    with pytest.raises(OwnershipConflict):
        authority.verify(c.spec.configuration, "start", c.op, control)
    assert c.channels == []
