"""Native3 lifecycle boundaries with explicit fake processes, no DB startup."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.sites.reddit.service_contract import (
    RedditServiceSpec,
    RedditPorts,
)
from lab_generate_skill.sites.reddit.service_commands import (
    container,
    service_commands,
    SERVICE_NAMES,
)
from lab_generate_skill.sites.reddit.service_programs import (
    SEED,
    CONFIGURE,
    TRUST_ACCOUNT,
)
from lab_generate_skill.sites.reddit.services import (
    RedditGeneration,
    seed,
    preflight,
    require_stop,
)
from reddit_services_fixtures import Commands, Group, spec
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


def roots(root: Path) -> None:
    for name in ["state", "control", "runtime"]:
        (root / name).mkdir(mode=0o700)


def test_seed_controls_original_private_mounts_and_native3_generation(
    node_path: Path,
) -> None:
    roots(node_path)
    selected = spec(node_path)
    commands = Commands(node_path)
    seed(selected, commands, guard())
    assert (node_path / "state/media-native").is_dir()
    assert all(
        (node_path / "control" / n).stat().st_mode & 0o777 == 0o600
        for n in ["php.conf", "nginx.conf", "pg_hba.conf"]
    )
    fpm = (node_path / "control/php.conf").read_text()
    nginx = (node_path / "control/nginx.conf").read_text()
    assert (
        "session.save_path]=/state/session" in fpm
        and "upload_tmp_dir]=/state/uploads" in fpm
    )
    assert (
        "/submission_images/" in nginx
        and "@original_native_media" in nginx
        and "/media/cache/" in nginx
    )
    assert "listen_addresses=" in service_commands(selected)["postgres"]
    assert container(selected)[-1] == selected.files.image_path
    assert str(node_path / "control") + ":/control:ro" in container(selected)
    assert str(node_path / "state/app.env") + ":/var/www/html/.env" in container(
        selected
    )
    assert str(node_path / "state/app.env") + ":/var/www/html/.env" not in container(
        selected, seeded=False
    )
    group = Group()
    generation = RedditGeneration(selected, commands, group)
    assert generation.start(guard(), initialize=True) == selected.endpoint
    assert (
        group.names == list(SERVICE_NAMES)
        and tuple(p.service for p in generation.pins) == SERVICE_NAMES
    )
    assert sum(TRUST_ACCOUNT in c for c in commands.calls) == 1
    stopped = generation.quiesce(guard())
    require_stop(stopped, generation.pins)
    with pytest.raises(InvalidTransition):
        generation.quiesce(guard())
    with pytest.raises(InvalidTransition):
        generation.start(guard(), initialize=True)
    generation.stop(guard())
    assert group.stopped
    resumed_commands = Commands(node_path)
    resumed = RedditGeneration(selected, resumed_commands, Group(1))
    resumed.start(guard(), initialize=False)
    assert not any(TRUST_ACCOUNT in c for c in resumed_commands.calls)


@pytest.mark.parametrize(
    "failure",
    ["postgres", "php", "nginx", "pin-postgres", "pin-php", "pin-nginx", "quiesce"],
)
def test_partial_start_or_stop_retains_handles_and_cannot_restart(
    node_path: Path, failure: str
) -> None:
    group = Group()
    group.fail = failure
    generation = RedditGeneration(spec(node_path), Commands(node_path), group)
    with pytest.raises((OSError, TimeoutError)):
        generation.start(guard(), initialize=True)
        generation.quiesce(guard())
    assert generation.state == "failed" and group.names
    generation.stop(guard())
    assert group.stopped
    with pytest.raises(InvalidTransition):
        generation.start(guard(), initialize=True)


@pytest.mark.parametrize("which", ["health", "account"])
def test_malformed_native_returns_never_start_frontend(
    node_path: Path, which: str
) -> None:
    commands = Commands(node_path)
    group = Group()
    if which == "health":
        commands.health = b"not-a-health-reply"
    else:
        commands.trusted = b"trusted"
    generation = RedditGeneration(spec(node_path), commands, group)
    with pytest.raises(ValueError):
        generation.start(guard(), initialize=True)
    assert group.names == ["postgres"] and generation.state == "failed"
    generation.stop(guard())


@pytest.mark.parametrize("code", [1, 143, -15, -9])
def test_nonzero_native_exit_never_authorizes_snapshot(
    node_path: Path, code: int
) -> None:
    group = Group()
    generation = RedditGeneration(spec(node_path), Commands(node_path), group)
    generation.start(guard(), initialize=False)
    group.exitcode = code
    with pytest.raises(ValueError, match="exit normally"):
        generation.quiesce(guard())
    assert (
        generation.state == "failed"
        and generation.quiescence is not None
        and all(m.returncode == code for m in generation.quiescence.masters)
    )
    generation.stop(guard())


def test_wrong_original_namespace_or_order_is_refused(node_path: Path) -> None:
    group = Group()
    generation = RedditGeneration(spec(node_path), Commands(node_path), group)
    generation.start(guard(), initialize=False)
    facts = generation.quiesce(guard())
    with pytest.raises(ValueError):
        require_stop(facts, tuple(reversed(generation.pins)))
    wrong = generation.pins[0].model_copy(update={"namespace_inode": 999999})
    with pytest.raises(ValueError):
        require_stop(facts, (wrong, *generation.pins[1:]))


@pytest.mark.parametrize(
    "kind", ["dirty", "symlink", "configure", "duplicate-controls"]
)
def test_seed_failure_never_falls_back_or_overwrites(
    node_path: Path, kind: str
) -> None:
    roots(node_path)
    commands = Commands(node_path)
    selected = spec(node_path)
    if kind == "dirty":
        (node_path / "state/existing").write_text("keep")
    elif kind == "symlink":
        (node_path / "state").rmdir()
        (node_path / "state").symlink_to(
            node_path / "runtime", target_is_directory=True
        )
    elif kind == "configure":
        commands.configure = b"partial"
    else:
        (node_path / "control/php.conf").write_text("keep")
    with pytest.raises((ValueError, FileExistsError)):
        seed(selected, commands, guard())
    if kind in ("dirty", "symlink"):
        assert commands.calls == []
    if kind == "duplicate-controls":
        assert (node_path / "control/php.conf").read_text() == "keep"


@pytest.mark.parametrize("value", [None, True, "12001", 0, 1023, 65536, [], 10**200])
def test_port_illegal_types_and_ranges_before_effect(value: Any) -> None:
    with pytest.raises(ValueError):
        RedditPorts(web=value, database=12002)


@pytest.mark.parametrize("ports", [(1024, 65535), (65535, 1024)])
def test_port_boundaries_and_duplicate_refusal(ports: tuple[int, int]) -> None:
    assert RedditPorts(web=ports[0], database=ports[1]).web == ports[0]
    with pytest.raises(ValueError):
        RedditPorts(web=ports[0], database=ports[0])


@pytest.mark.parametrize(
    "change",
    [
        {"sha256": "a" * 64},
        {"size_bytes": 1},
        {"executable": True},
        {"path": "other.sif"},
    ],
)
def test_wrong_original_image_denied(node_path: Path, change: dict[str, Any]) -> None:
    data = spec(node_path).model_dump(mode="json")
    data["files"]["image"].update(change)
    with pytest.raises(ValueError):
        RedditServiceSpec.model_validate_json(json.dumps(data))


def test_preflight_has_no_seed_or_services_and_cancel_does_not_start(
    node_path: Path,
) -> None:
    commands = Commands(node_path)
    selected = spec(node_path)
    preflight(selected, commands, guard())
    assert len(commands.calls) == 5 and not any(
        "-ec" in c or TRUST_ACCOUNT in c for c in commands.calls
    )
    from lab_generate_skill.sites.reddit.media_initialization_program import (
        INITIALIZE_MEDIA,
    )

    assert sum("if(false){" + INITIALIZE_MEDIA + "}" in c for c in commands.calls) == 1
    group = Group()
    generation = RedditGeneration(selected, commands, group)

    class Cancelled:
        def checkpoint(self) -> float:
            raise TimeoutError("cancelled")

        def wait(self, seconds: float) -> None:
            raise TimeoutError("cancelled")

    with pytest.raises(TimeoutError):
        generation.start(Cancelled(), initialize=True)
    assert group.names == [] and generation.state == "new"
