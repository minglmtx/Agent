"""Small deterministic command-runner checks; no LLM or network required."""
import asyncio
import os
from pathlib import Path
import shlex
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mini_claude.command_runner import run_command, cancel_all_commands


def py(code):
    return f"{shlex.quote(sys.executable)} -u -c {shlex.quote(code)}"


def process_stopped(stat):
    """The kernel can reap a process between an exists check and reading stat."""
    try:
        return stat.read_text().split()[2] == "Z"
    except FileNotFoundError:
        return True


@unittest.skipUnless(os.name == "posix", "POSIX process groups required")
class CommandRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_cmd(self, command, **kwargs):
        return run_command(command, log_dir=self.tmp.name, **kwargs)

    def test_streaming_before_exit_and_stderr(self):
        stamps = []
        start = time.monotonic()
        result = self.run_cmd(py("import time,sys; print('ready'); time.sleep(.35); print('warning',file=sys.stderr)"),
                              on_output=lambda channel, text: stamps.append((channel, text, time.monotonic() - start)))
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("warning", result.stderr)
        self.assertTrue(stamps)
        self.assertLess(stamps[0][2], result.duration_s - .15)
        self.assertEqual(Path(result.log_path).stat().st_mode & 0o777, 0o600)

    def test_timeout_keeps_partial_output(self):
        result = self.run_cmd(py("import time; print('before timeout'); time.sleep(10)"), timeout_s=.2)
        self.assertEqual(result.status, "timed_out")
        self.assertIn("before timeout", result.stdout)
        self.assertIn("before timeout", Path(result.log_path).read_text())
        self.assertLess(result.duration_s, 2)

    def test_cancel_all_cleans_ignoring_descendant(self):
        ready = threading.Event()
        results = []
        # The child ignores TERM; group KILL must stop it too.
        child = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(20)"
        code = f"import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-u','-c',{child!r}]); print(p.pid); time.sleep(20)"
        worker = threading.Thread(target=lambda: results.append(self.run_cmd(py(code), on_output=lambda *_: ready.set())))
        worker.start()
        try:
            self.assertTrue(ready.wait(3))
            self.assertGreaterEqual(cancel_all_commands(), 1)
            worker.join(3)
            self.assertFalse(worker.is_alive())
            result = results[0]
            self.assertEqual(result.status, "cancelled")
            pid = int(result.stdout.strip())
            stat = Path(f"/proc/{pid}/stat")
            # Zombies are stopped, awaiting the host's init process to reap them.
            self.assertTrue(process_stopped(stat))
        finally:
            cancel_all_commands()
            worker.join(3)

    def test_output_and_log_are_bounded(self):
        result = self.run_cmd(py("print('x'*200000)"), max_output_bytes=1024, max_log_bytes=4096)
        self.assertEqual(result.status, "completed")
        self.assertTrue(result.output_truncated)
        self.assertTrue(result.log_truncated)
        self.assertLessEqual(len(result.stdout.encode()), 1024)
        self.assertLessEqual(Path(result.log_path).stat().st_size, 4096)

    def test_failure_and_callback_exception(self):
        def bad_callback(*_):
            raise RuntimeError("UI failure")
        result = self.run_cmd(py("import sys; print('detail',file=sys.stderr); sys.exit(7)"), on_output=bad_callback)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.exit_code, 7)
        self.assertIn("detail", result.render())

    def test_background_child_does_not_outlive_successful_command(self):
        code = "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); print(p.pid)"
        result = self.run_cmd(py(code))
        self.assertEqual(result.status, "completed")
        pid = int(result.stdout.strip())
        stat = Path(f"/proc/{pid}/stat")
        deadline = time.monotonic() + 1
        while not process_stopped(stat) and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(process_stopped(stat))

    def test_precancelled_command_does_not_execute(self):
        event = threading.Event()
        event.set()
        target = Path(self.tmp.name) / "side-effect"
        result = self.run_cmd(py(f"open({str(target)!r}, 'w').write('bad')"), cancel_event=event)
        self.assertEqual(result.status, "cancelled")
        self.assertFalse(target.exists())
        self.assertIsNone(result.exit_code)


@unittest.skipUnless(os.name == "posix", "POSIX process groups required")
class ToolCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_cancellation_stops_command_before_return(self):
        from mini_claude.tools import execute_tool, set_shell_output_callback
        ready = threading.Event()
        chunks = []
        def callback(stream, text):
            chunks.append(text)
            ready.set()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"MINI_CLAUDE_STATE_DIR": tmp}):
            set_shell_output_callback(callback)
            task = asyncio.create_task(execute_tool("run_shell", {"command": py("import os,time; print(os.getpid()); time.sleep(20)")}))
            try:
                self.assertTrue(await asyncio.to_thread(ready.wait, 3))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                pid = int("".join(chunks).strip())
                stat = Path(f"/proc/{pid}/stat")
                self.assertTrue(process_stopped(stat))
            finally:
                set_shell_output_callback(None)
                cancel_all_commands()


if __name__ == "__main__":
    unittest.main()
