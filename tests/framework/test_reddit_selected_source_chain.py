"""Selected C through shared source AB: original initial records and complete reset."""

from pathlib import Path
from typing import Any
import pytest
from reddit_source_selection import RedditSourceSelection
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from reddit_forum_source_fixtures import CONTRACT, public
from test_reddit_source_assembly import check_shared_source
from site_instance_fixtures import node_path as node_path
from qualified_source_native import QualifiedSource, configure_qualification
from site_resource_fixtures import resource_case
from test_site_resource_installed import run_registered_site_case
from source_task_hooks import SourceTaskHooks
from evidence_control_fixtures import EvidenceFixtureStore


@pytest.mark.parametrize("fault", ["none", "wrong_snapshot", "missing_closure"])
def test_selected_forum_source_preparation_unique_initial_and_safe_reset(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    check_shared_source(
        tmp_path,
        node_path,
        monkeypatch,
        fault,
        RedditSourceSelection(CONTRACT.read_bytes(), public()),
    )


@pytest.mark.parametrize(
    "invalid",
    [None, "", 1, [], b"", b"{}", b" " * (1024 * 1024 + 1)],
    ids=["none", "text", "integer", "list", "empty-bytes", "empty-object", "oversize"],
)
def test_selection_invalid_native_before_source_effects(invalid: Any) -> None:
    expected = EvidenceIntegrityError if invalid == b"{}" else ValueError
    with pytest.raises(expected):
        RedditSourceSelection(invalid, public())


@pytest.mark.parametrize("invalid", [None, {}, 1, ""])
def test_selection_requires_typed_public_input(invalid: Any) -> None:
    with pytest.raises(TypeError):
        RedditSourceSelection(CONTRACT.read_bytes(), invalid)


def test_selection_maps_only_allocated_public_start_and_actions() -> None:
    selected = RedditSourceSelection(CONTRACT.read_bytes(), public())
    task = selected.public_at("http://127.0.0.1:12001/", None)
    assert task.identity == public().identity and task.goal == public().goal
    assert task.start_url == "http://127.0.0.1:12001/forums/all"
    assert selected.public_at("http://127.0.0.1:12001/", None) == task
    for endpoint in (
        "http://remote:12001/",
        "http://127.0.0.1:1/",
        "http://127.0.0.1:12001/submit",
    ):
        with pytest.raises(EvidenceIntegrityError) as caught:
            selected.public_at(endpoint, None)
        assert isinstance(caught.value.__cause__, ValueError)
    with pytest.raises(EvidenceIntegrityError) as caught:
        selected.public_at("http://127.0.0.1:12001/", ("click",))
    assert isinstance(caught.value.__cause__, ValueError)


def test_foreign_site_selection_refused_before_publication_or_resource_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = resource_case(tmp_path, monkeypatch)
    selected = RedditSourceSelection(CONTRACT.read_bytes(), public())
    before = tuple(sorted((tmp_path / "evidence/blobs").iterdir()))
    with pytest.raises(ValueError):
        configure_qualification(c, reddit_selection=selected)
    absent: Any = None
    with pytest.raises(ValueError):
        QualifiedSource(c, absent, absent, reddit_selection=selected)
    assert (
        tuple(sorted((tmp_path / "evidence/blobs").iterdir())) == before
        and not c.channels
    )
    hooks = SourceTaskHooks(
        c.spec.token.owner,
        EvidenceFixtureStore(tmp_path / "evidence"),
        public().allowed_actions,
        lambda *args: None,
        lambda *args: None,
        reddit_selection=selected,
    )
    with pytest.raises(ValueError):
        run_registered_site_case(
            absent,
            tmp_path,
            monkeypatch,
            "qualified_source",
            task_hooks=hooks,
            site_id="shopping_admin",
        )


@pytest.mark.parametrize("invalid", [{}, [], "", b"", 1, False])
def test_selection_type_refused_before_configuration_or_source_effects(
    tmp_path: Path, invalid: Any
) -> None:
    absent: Any = None
    with pytest.raises(TypeError, match="Explicit validated Reddit selection"):
        configure_qualification(absent, reddit_selection=invalid)
    with pytest.raises(TypeError, match="Explicit validated Reddit selection"):
        QualifiedSource(absent, absent, absent, reddit_selection=invalid)
    assert list(tmp_path.iterdir()) == []
