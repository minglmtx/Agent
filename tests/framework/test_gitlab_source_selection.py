"""Explicit actual source declarations fail before publication/resource effects."""

from pathlib import Path
from typing import Any
from types import SimpleNamespace
import pytest
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec
from lab_generate_skill.sites.gitlab.tasks.ssh_key_spec import SshKeySpec
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from gitlab_source_selection import (
    GitlabSourceSelection,
    group_selection,
    ssh_selection,
)
from gitlab_preparation_native import GitlabPreparation
from gitlab_site_native_plan import private_site_plan
from qualified_source_native import configure_qualification, QualifiedSource
from site_resource_fixtures import resource_case
from site_storage_fixtures import private_configuration
from source_task_hooks import SourceTaskHooks
from test_site_resource_installed import run_registered_site_case


def config_at(root: Path, selected: GitlabSourceSelection) -> SiteWorkerConfiguration:
    base = private_configuration(root)
    assert base.private_evidence is not None
    return base.model_copy(
        update={
            "private_evidence": base.private_evidence.model_copy(
                update={"profile": selected.profile}
            )
        }
    )


@pytest.mark.parametrize("group", [False, True])
def test_explicit_source_binds_original_contract_and_family_records_inertly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    group: bool,
) -> None:
    selected = group_selection() if group else ssh_selection()
    c = resource_case(tmp_path, monkeypatch, config=config_at(tmp_path, selected))
    spec = configure_qualification(c, gitlab_selection=selected)
    n = GitlabPreparation(
        c, "http://127.0.0.1:12001/", state_spec=spec, selection=selected
    )
    private = (
        GroupSpec.model_validate_json(n.private_input_json())
        if group
        else SshKeySpec.model_validate_json(n.private_input_json())
    )
    assert private == n.task_spec and private.task == selected.public_template.identity
    assert (
        private.admission == "unverified"
        and n.native_contract_ref == private.native_contract_ref
    )
    assert n.bindings.load(n.binding_ref, c.op) == n.binding
    assert n.recovery.restore_component_id == (
        "gitlab-group-creation" if group else "gitlab-profile-ssh-key"
    )
    assert n.public.start_url == "http://127.0.0.1:12001/" + (
        "groups/new" if group else ""
    )
    assert n.request is None and n.result is None and not c.channels
    assert selected.public_at("http://127.0.0.1:12001/", None) == n.public
    assert selected.public_at("http://127.0.0.1:12001/", None) == n.public


@pytest.mark.parametrize("group", [False, True])
@pytest.mark.parametrize(
    "fault", ["missing", "opposite-profile", "opposite-policy", "foreign-site"]
)
def test_missing_or_cross_family_source_rejected_before_new_persistent_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    group: bool,
    fault: str,
) -> None:
    selected, other = (
        (group_selection(), ssh_selection())
        if group
        else (ssh_selection(), group_selection())
    )
    config = config_at(tmp_path, other if fault == "opposite-profile" else selected)
    if fault == "foreign-site":
        from site_worker_fixtures import configuration

        config = configuration(job_id="4752096")
    c = resource_case(tmp_path, monkeypatch, config=config)
    before = tuple(sorted((tmp_path / "evidence/blobs").iterdir()))
    absent: Any = None
    with pytest.raises(ValueError):
        if fault == "opposite-policy":
            GitlabPreparation(
                c,
                "http://127.0.0.1:12001/",
                state_spec=other.initial_spec,
                selection=selected,
            )
        elif fault == "missing":
            configure_qualification(c)
        else:
            configure_qualification(c, gitlab_selection=selected)
    with pytest.raises(ValueError):
        site: Any = (
            SimpleNamespace(
                site=SimpleNamespace(
                    instance=SimpleNamespace(endpoint="http://127.0.0.1:12001/")
                )
            )
            if fault == "opposite-policy"
            else absent
        )
        QualifiedSource(
            c,
            site,
            other.initial_spec if fault == "opposite-policy" else absent,
            gitlab_selection=None if fault == "missing" else selected,
        )
    assert (
        tuple(sorted((tmp_path / "evidence/blobs").iterdir())) == before
        and not c.channels
    )


@pytest.mark.parametrize(
    "bad",
    [None, "", 1, [], b"", b"{}", b" " * (1024 * 1024 + 1)],
    ids=["none", "text", "integer", "list", "empty", "empty-object", "oversize"],
)
def test_invalid_native_contract_is_not_a_source_declaration(bad: Any) -> None:
    expected = EvidenceIntegrityError if bad == b"{}" else ValueError
    with pytest.raises(expected):
        GitlabSourceSelection(bad, group_selection().public_template)


@pytest.mark.parametrize("bad", [None, {}, 1, ""])
def test_only_validated_public_template_is_accepted(bad: Any) -> None:
    with pytest.raises(TypeError):
        GitlabSourceSelection(group_selection().native, bad)


@pytest.mark.parametrize("bad", [{}, [], "", b"", 1, False])
def test_wrong_type_selection_fails_before_configuration_access(bad: Any) -> None:
    absent: Any = None
    with pytest.raises(TypeError, match="Explicit validated GitLab selection"):
        configure_qualification(absent, gitlab_selection=bad)
    with pytest.raises(TypeError, match="Explicit validated GitLab selection"):
        QualifiedSource(absent, absent, absent, gitlab_selection=bad)


@pytest.mark.parametrize("group", [False, True])
@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        None,
        1,
        "http://remote:12001/",
        "http://127.0.0.1:1/",
        "http://127.0.0.1:12001/x/",
        "http://127.0.0.1:12001/?x=1",
    ],
)
def test_bad_allocated_origin_never_publishes_selected_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    group: bool,
    endpoint: Any,
) -> None:
    selected = group_selection() if group else ssh_selection()
    c = resource_case(tmp_path, monkeypatch, config=config_at(tmp_path, selected))
    before = tuple(sorted((tmp_path / "evidence/blobs").iterdir()))
    with pytest.raises((TypeError, ValueError)):
        GitlabPreparation(
            c, endpoint, state_spec=selected.initial_spec, selection=selected
        )
    assert (
        tuple(sorted((tmp_path / "evidence/blobs").iterdir())) == before
        and not c.channels
    )


def test_foreign_hook_cannot_reach_slurm_or_omit_selected_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = group_selection()
    c = resource_case(tmp_path, monkeypatch, config=config_at(tmp_path, selected))
    hook = SourceTaskHooks(
        c.spec.token.owner,
        c.evidence,
        selected.public_template.allowed_actions,
        lambda *args: None,
        lambda *args: None,
        gitlab_selection=selected,
    )
    absent: Any = None
    with pytest.raises(ValueError, match="original source entry"):
        run_registered_site_case(
            absent,
            tmp_path,
            monkeypatch,
            "qualified_source",
            task_hooks=hook,
            site_id="shopping_admin",
        )
    with pytest.raises(ValueError, match="explicit original selection"):
        run_registered_site_case(
            absent, tmp_path, monkeypatch, "qualified_source", site_id="gitlab"
        )
    from map_source_live import run_source
    from map_source_inputs import engineering_scope

    with pytest.raises(ValueError, match="Foreign selected input"):
        run_source(
            absent,
            tmp_path,
            monkeypatch,
            hook,
            scope=engineering_scope(hook.owner, None),
            evidence_root=tmp_path / "evidence",
        )
    assert not c.channels


def test_group_private_profile_declaration_is_inert_and_exact(tmp_path: Path) -> None:
    from site_worker_fixtures import configuration

    base = configuration(job_id="4752096")
    selected = group_selection()
    plan = private_site_plan(
        base.token.owner,
        base.installation,
        evidence_root=tmp_path / "evidence",
        session_root=tmp_path / "sessions",
        journal_root=tmp_path / "journal",
        selection=selected,
    )
    assert (
        plan.profile == selected.profile
        and EvidenceStorageConfig.model_validate(plan.config) == plan.config
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("group", [False, True])
@pytest.mark.parametrize("port", [1024, 65535])
def test_allocated_origin_port_boundaries_preserve_frozen_source(
    group: bool, port: int
) -> None:
    selected = group_selection() if group else ssh_selection()
    task = selected.public_at(f"http://127.0.0.1:{port}/", None)
    assert (
        task.identity == selected.public_template.identity
        and task.goal == selected.public_template.goal
    )
    assert task.start_url == f"http://127.0.0.1:{port}/" + (
        "groups/new" if group else ""
    )


@pytest.mark.parametrize("group", [False, True])
def test_missing_native_terminal_action_is_rejected_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    group: bool,
) -> None:
    selected = group_selection() if group else ssh_selection()
    c = resource_case(tmp_path, monkeypatch, config=config_at(tmp_path, selected))
    before = tuple(sorted((tmp_path / "evidence/blobs").iterdir()))
    with pytest.raises(EvidenceIntegrityError):
        GitlabPreparation(
            c,
            "http://127.0.0.1:12001/",
            state_spec=selected.initial_spec,
            selection=selected,
            allowed_actions=("click",),
        )
    assert (
        tuple(sorted((tmp_path / "evidence/blobs").iterdir())) == before
        and not c.channels
    )
