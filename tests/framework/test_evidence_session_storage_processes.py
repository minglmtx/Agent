"""Same-node independent interpreters; synthetic authority, no real worker proof."""

import subprocess
import sys
import time
from pathlib import Path
from evidence_session_fixtures import binding, capacity, intent
from evidence_session_storage_fixtures import store

PROGRAM = """
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[2])  # Test fixtures only, never production bootstrap.
from evidence_session_fixtures import binding, intent
from evidence_session_storage_fixtures import store
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
root = Path(sys.argv[1]); label = sys.argv[3]
(root / (label + '.ready')).write_text('ready')
limit = time.monotonic() + 15
while not (root / 'start').exists():
    if time.monotonic() > limit: raise TimeoutError('unit barrier')
    time.sleep(.01)
ledger = store(root)
try:
    ledger.begin(binding(), intent(), 0)
    print('committed', flush=True)
except DispatchAlreadyCommitted:
    print('already', flush=True)
"""


def test_two_processes_commit_once_then_fresh_process_reads(tmp_path: Path) -> None:
    store(tmp_path).create(binding(), capacity(), intent().operation)
    children = [
        subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-c",
                PROGRAM,
                str(tmp_path),
                str(Path(__file__).parent),
                label,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for label in ("a", "b")
    ]
    try:
        limit = time.monotonic() + 15
        while not all((tmp_path / (label + ".ready")).exists() for label in ("a", "b")):
            assert time.monotonic() < limit, "children did not reach barrier"
            assert all(
                child.poll() is None for child in children
            ), "child failed before barrier"
            time.sleep(0.01)
        (tmp_path / "start").write_text("go")
        outputs = [child.communicate(timeout=20) for child in children]
        assert all(child.returncode == 0 for child in children), outputs
        assert sorted(out.strip() for out, _ in outputs) == ["already", "committed"]
        assert all(not err for _, err in outputs)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)
    read_program = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from evidence_session_fixtures import binding, intent
from evidence_session_storage_fixtures import store
snapshot = store(Path(sys.argv[1])).read(binding(), intent().operation)
assert snapshot.revision == 1 and snapshot.entries[0].stage == 'pending'
assert snapshot.entries[0].intent == intent()
print('original-pending')
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            read_program,
            str(tmp_path),
            str(Path(__file__).parent),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert completed.stdout.strip() == "original-pending"
