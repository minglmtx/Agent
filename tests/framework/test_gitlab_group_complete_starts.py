"""Whole original Group subgroup binds root/form starts, without granting execution."""

import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.gitlab_group import load_group_inputs
from lab_generate_skill.bootstrap.gitlab_group_browser_declarations import (
    group_browser_declaration,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)
from lab_generate_skill.sites.gitlab.browser_initialization import (
    GitlabGroupBrowserInitializer,
)
from gitlab_group_fixtures import reference
from gitlab_source_selection import GitlabSourceSelection
from test_gitlab_group_browser import GroupPage, selection
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
PINS = {
    "286d4ac488bdcd446ffc": "a81355982fc4c6d2c22c32bd35cf599acd84f3fb822fc364fd23ad73e2e0efc2",
    "b45c2140f3e8557e1708": "b97f06e7d7ae684a789b30c46cbeb1823a4bbe18215e3b5fd0f70020d81c9f1c",
    "e4d658cfba6588f6a386": "acd7e87bdbfbe2d18d093135bcbb1940d7cf259a13d7665511be8bc3437ce750",
    "f205b50137926a04a0e3": "230ae6bba309bac26ac69cc5fe70b56cb6eb512e0b7c809b618df49836792729",
}
ORIGIN = "http://127.0.0.1:18080/"


def original(source: str) -> tuple[bytes, dict[str, Any], PublicTask]:
    raw = (
        W
        / "experiments/sft-ordinary-source-bindings-v1/prepared/contracts"
        / (source + ".json")
    ).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PINS[source]
    native = json.loads(raw)
    public = PublicTask(
        identity=TaskIdentity(
            site="gitlab",
            family="group_creation",
            contract_version=1,
            split="train",
            task_id=source,
            source_task_id=source,
        ),
        goal=native["goal"],
        start_url=ORIGIN + native["start_path"].removeprefix("/"),
        allowed_actions=("click", "fill", "send_msg_to_user"),
    )
    return raw, native, public


@pytest.mark.parametrize("source", tuple(PINS))
def test_whole_group_keeps_native_start_requirements_and_single_initialized_view(
    source: str,
) -> None:
    raw, native, public = original(source)
    private = load_group_inputs(raw, reference(raw), public)
    assert private.admission == "unverified" and not native["eligible_for_training"]
    assert (
        json.loads(private.model_dump_json())["requirements"]
        == native["group_creation"]
    )
    assert load_group_inputs(raw, reference(raw), public) == private
    selected = GitlabSourceSelection(raw, public)
    allocated = selected.public_at("http://127.0.0.1:12010/", None)
    assert allocated.start_url == "http://127.0.0.1:12010" + native["start_path"]
    measured = selection("http://127.0.0.1:12010/")
    config = group_browser_declaration(
        allocated,
        measured.endpoint,
        measured.native_account_id,
        measured.prepared_ref,
        measured.site_ref,
    )
    assert ("start_path" in config.model_dump()) == (
        native["start_path"] != "/groups/new"
    )
    assert config == GitlabGroupInitialization.model_validate_json(
        config.model_dump_json()
    )
    config.check_task(allocated)
    page = GroupPage()
    setup = GitlabGroupBrowserInitializer(
        config, lambda control: ("native-user", "private-password")
    )
    setup.setup(page, allocated, guard())
    assert page.url == allocated.start_url
    assert page.calls == ["route", "new_page", "goto", "account_ready", "account_id"]
    assert page.login.calls.count("fill") == 2 and page.login.calls[-1] == "close"
    assert "fill" not in page.calls and "click" not in page.calls
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, allocated, guard())
    foreign_start = ORIGIN + ("groups/new" if native["start_path"] == "/" else "")
    wrong = PublicTask.model_validate(
        public.model_copy(update={"start_url": foreign_start})
    )
    with pytest.raises(EvidenceIntegrityError):
        load_group_inputs(raw, reference(raw), wrong)


@pytest.mark.parametrize(
    "recorded", [None, [], ["/", "/"], [3], ["/foreign"], ["/groups/new"]]
)
def test_root_requires_nonempty_unique_typed_original_recorded_starts(
    recorded: Any,
) -> None:
    _, native, public = original("286d4ac488bdcd446ffc")
    native["recorded_start_paths"] = recorded
    raw = json.dumps(native).encode()
    with pytest.raises(EvidenceIntegrityError):
        load_group_inputs(raw, reference(raw), public)


def test_legacy_group_configuration_bytes_stay_unchanged_without_new_declaration() -> (
    None
):
    legacy = selection()
    raw = legacy.model_dump_json()
    assert "start_path" not in json.loads(raw)
    assert GitlabGroupInitialization.model_validate_json(raw).model_dump_json() == raw
    assert GitlabGroupInitialization.model_validate(legacy).model_dump_json() == raw
    _, _, public = original("e4d658cfba6588f6a386")
    assert (
        group_browser_declaration(
            public,
            legacy.endpoint,
            legacy.native_account_id,
            legacy.prepared_ref,
            legacy.site_ref,
        ).model_dump_json()
        == raw
    )
    declared = GitlabGroupInitialization.model_validate(
        {**legacy.model_dump(), "start_path": "/"}
    )
    assert json.loads(declared.model_dump_json())["start_path"] == "/"
    assert (
        GitlabGroupInitialization.model_validate_json(declared.model_dump_json())
        == declared
    )


@pytest.mark.parametrize("source", tuple(PINS))
def test_complete_group_preparation_unique0_and_closed_binding_records(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    # Each source uses its real complete native contract, with synthetic
    # native SQL/services/kernel/page premises. Nothing qualifies a live source.
    from test_gitlab_group_initial_observation import (
        test_group_original_records_join_common_binding_and_unique_initial as check_initial,
    )
    import gitlab_group_fixtures as originals
    import gitlab_group_preparation_fixtures as preparations

    original(source)
    path = (
        W
        / "experiments/sft-ordinary-source-bindings-v1/prepared/contracts"
        / (source + ".json")
    )
    monkeypatch.setattr(originals, "FIXTURE", path)
    monkeypatch.setattr(preparations, "FIXTURE", path)
    check_initial(tmp_path, node_path, monkeypatch, "none")
