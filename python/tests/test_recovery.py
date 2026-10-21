"""Deterministic crash-window and journal tests; no model or network required."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from mini_claude import session
from mini_claude.execution_journal import (
    ExecutionJournal, JournalConflict, JournalCorruption, UnknownExecution,
)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.session_patch = patch.object(session, "SESSION_DIR", self.root / "sessions")
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)

    def journal(self):
        return ExecutionJournal("demo", self.root / "journals")

    def test_interrupted_atomic_save_preserves_previous_session(self):
        old = {"metadata": {"id": "demo"}, "messages": [{"role": "user", "content": "old"}]}
        session.save_session("demo", old)
        with patch.object(session.os, "replace", side_effect=OSError("injected crash")):
            with self.assertRaises(OSError):
                session.save_session("demo", {"messages": []})
        self.assertEqual(session.load_session("demo"), old)
        self.assertEqual(list(session.SESSION_DIR.glob("*.tmp")), [])

    def test_completed_call_reuses_result_without_repeat_and_rejects_conflict(self):
        log = self.journal()
        calls = []
        for _ in range(2):
            cached = log.begin("call-1", "write_file", {"path": "out", "content": "one"})
            if cached is None:
                calls.append("write")
                log.complete("call-1", "written")
            else:
                self.assertEqual(cached, "written")
        self.assertEqual(calls, ["write"])
        self.assertEqual(self.journal().lookup("call-1")["result"], "written")
        with self.assertRaises(JournalConflict):
            log.begin("call-1", "write_file", {"path": "out", "content": "two"})

    def test_unknown_effect_survives_restart_and_acknowledgement_is_not_replay(self):
        self.journal().begin("call-2", "bash", {"command": "touch output"})
        restored = self.journal()
        self.assertEqual(restored.lookup("call-2")["state"], "unknown")
        self.assertEqual(len(restored.unresolved()), 1)
        with self.assertRaises(UnknownExecution):
            restored.begin("call-2", "bash", {"command": "touch output"})
        restored.mark_unknown("call-2", "process interrupted")
        restored.acknowledge_unknown("call-2", "User inspected output file")
        self.assertEqual(restored.unresolved(), [])
        with self.assertRaises(UnknownExecution):
            restored.begin("call-2", "bash", {"command": "touch output"})
        self.assertEqual(restored.lookup("call-2")["state"], "acknowledged")

    def test_duplicate_concurrent_begin_only_one_starts(self):
        def attempt(_):
            try:
                self.journal().begin("same", "bash", {"command": "echo ok"})
                return "started"
            except UnknownExecution:
                return "blocked"
        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = list(pool.map(attempt, range(6)))
        self.assertEqual(outcomes.count("started"), 1)
        self.assertEqual(outcomes.count("blocked"), 5)

    def test_corrupt_files_fail_explicitly_and_remain_unchanged(self):
        session.SESSION_DIR.mkdir()
        path = session.SESSION_DIR / "broken.json"
        path.write_text('{"messages":')
        with self.assertRaises(session.SessionCorruption):
            session.load_session("broken")
        self.assertEqual(path.read_text(), '{"messages":')
        log = self.journal()
        log.begin("a", "read_file", {"path": "a"})
        with log.path.open("a") as stream:
            stream.write('{"call_id":')
        with self.assertRaises(JournalCorruption):
            log.begin("b", "read_file", {"path": "b"})

    def test_session_ids_cannot_escape_directory_and_invalid_shape_is_corruption(self):
        for name in ("../escape", "/tmp/escape", "", ".hidden"):
            with self.assertRaises(ValueError):
                session.save_session(name, {"messages": []})
            with self.assertRaises(ValueError):
                ExecutionJournal(name, self.root)
        session.SESSION_DIR.mkdir()
        (session.SESSION_DIR / "bad.json").write_text(json.dumps({"messages": "oops"}))
        with self.assertRaises(session.SessionCorruption):
            session.load_session("bad")


if __name__ == "__main__":
    unittest.main()
