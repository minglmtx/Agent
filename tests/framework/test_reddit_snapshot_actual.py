"""Original image copier/parser on small trees and read-only seed file kinds."""

import json
import os
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.sites.reddit.snapshot import RedditSnapshots
from lab_generate_skill.sites.reddit.service_commands import container
from reddit_native_program_fixture import IMAGE, OriginalImageCommands
from reddit_tree_control_fixture import PAYLOADS, contents, prepare_tree
from reddit_snapshot_fixtures import stopped
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def record(name: str, value: object) -> None:
    root = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    (root / name).write_text(json.dumps(value, indent=2) + "\n")


def test_new_snapshot_fixture_covers_mutable_application_paths_without_native_pg(
    node_path: Path,
) -> None:
    selected = prepare_tree(node_path)
    before = contents(Path(selected.files.state_root))
    assert set(before) == set(PAYLOADS) | {"app.env"}
    assert all(value for value in before.values())
    assert (node_path / "state/postgres/PG_VERSION").read_bytes() == b"14\n"
    assert not (node_path / "state/postgres/global/pg_control").exists()
    assert not Path(selected.snapshot_root).exists()


def test_actual_original_image_full_small_tree_restored_and_backup_readonly(
    node_path: Path,
) -> None:
    selected = prepare_tree(node_path)
    commands = OriginalImageCommands(selected)
    state = Path(selected.files.state_root)
    before = contents(state)
    snapshots = RedditSnapshots(selected, commands)
    first, pins = stopped()
    saved = snapshots.save(first, pins, guard(60))
    for name in PAYLOADS:
        (state / name).write_bytes(b"changed payload")
    (state / "app.env").write_text("changed configuration\n")
    (state / "extra-auxiliary").write_bytes(b"new auxiliary file")
    second, newpins = stopped(1)
    restored = snapshots.restore(saved, second, newpins, guard(60))
    assert restored == saved.inventory and contents(state) == before
    assert selected.snapshot_root + ":/snapshot:ro" in next(
        c for c in commands.calls if "clear" in c
    )
    record(
        "reddit-native-small-tree.json",
        dict(
            passed=True,
            actual_database_started=False,
            original_service_stop_is_explicit_fake=True,
            source_image=str(IMAGE),
            snapshot=saved.inventory.model_dump(mode="json"),
            restored=restored.model_dump(mode="json"),
            restored_paths=sorted(before),
            whole_native_site_accepted=False,
        ),
    )


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_actual_native_inventory_refuses_unsafe_entry_before_copy(
    node_path: Path, kind: str
) -> None:
    selected = prepare_tree(node_path)
    commands = OriginalImageCommands(selected)
    path = node_path / "state/unsafe"
    if kind == "symlink":
        path.symlink_to(node_path / "outside")
    elif kind == "hardlink":
        os.link(node_path / "state/app.env", path)
    else:
        os.mkfifo(path, 0o600)
    snapshots = RedditSnapshots(selected, commands)
    first, pins = stopped()
    with pytest.raises(CommandFailure):
        snapshots.save(first, pins, guard(30))
    assert snapshots.saving and snapshots.result is None
    assert not any("/bin/cp" in c for c in commands.calls)
    assert not (Path(selected.snapshot_root) / "state").exists()


def test_actual_original_pg_seed_has_only_supported_directory_and_file_types(
    node_path: Path,
) -> None:
    selected = prepare_tree(node_path)
    commands = OriginalImageCommands(selected)
    program = r"""
$root='/usr/local/pgsql/data';$iterator=new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root,FilesystemIterator::SKIP_DOTS),RecursiveIteratorIterator::SELF_FIRST);
$files=0;$dirs=1;$bad=[];$total=0;
foreach($iterator as$entry){if(++$total>1000000)throw new RuntimeException('Native seed metadata bound');$s=lstat($entry->getPathname());
 if($entry->isLink()||(!$entry->isFile()&&!$entry->isDir())||($entry->isFile()&&$s['nlink']!==1)){if(count($bad)<10)$bad[]=substr($entry->getPathname(),strlen($root)+1);continue;}
 if($entry->isDir())$dirs++;else$files++;
}
echo json_encode(['schema_version'=>'reddit-original-pg-layout/1','files'=>$files,'directories'=>$dirs,'unsupported_entries'=>$bad,'version'=>trim(file_get_contents($root.'/PG_VERSION')),'metadata_only'=>true,'database_started'=>false],JSON_THROW_ON_ERROR);
"""
    raw = commands.run(
        container(selected, seeded=False) + ("/usr/local/bin/php", "-r", program),
        guard(60),
    )
    value = json.loads(raw)
    record("reddit-original-pg-layout.json", value)
    assert value["metadata_only"] and not value["database_started"]
    assert (
        value["version"] == "14"
        and value["files"] > 0
        and value["unsupported_entries"] == []
    )
