"""Recovery at the actual Agent dispatch boundary, with no API calls."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from mini_claude.agent import Agent
from mini_claude import session
from mini_claude.execution_journal import UnknownExecution
from mini_claude.session_lock import SessionBusy, session_lease


def tool_call(call_id="pending"):
    return {"role": "assistant", "content": "", "tool_calls": [{
        "id": call_id, "type": "function",
        "function": {"name": "write_file", "arguments": '{"path":"output","content":"done"}'},
    }]}


class AgentRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"MINI_CLAUDE_STATE_DIR": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.sessions = patch.object(session, "SESSION_DIR", self.root / "sessions")
        self.sessions.start()
        self.addCleanup(self.sessions.stop)

    def agent(self):
        agent = Agent(api_base="http://127.0.0.1:1/v1", api_key="test", model="test-model",
                      is_sub_agent=True, custom_system_prompt="Test agent")
        agent._mcp_initialized = True
        return agent

    async def test_checkpoint_with_call_is_durable_before_effect(self):
        agent = self.agent()
        agent._openai_messages.append(tool_call())
        effects = []

        async def dispatch(name, args):
            saved = session.load_session(agent.session_id)
            self.assertEqual(saved["openaiMessages"][-1]["tool_calls"][0]["id"], "pending")
            self.assertEqual(agent._journal.lookup("pending")["state"], "unknown")
            effects.append((name, args))
            return "saved"

        agent._dispatch_tool = dispatch
        result = await agent._execute_tool_call("write_file", {"path": "output", "content": "done"}, "pending")
        self.assertEqual(result, "saved")
        self.assertEqual(len(effects), 1)
        self.assertEqual(agent._journal.lookup("pending")["state"], "completed")

    async def test_failed_checkpoint_prevents_effect_and_journal_start(self):
        agent = self.agent()
        agent._dispatch_tool = AsyncMock(return_value="saved")
        with patch("mini_claude.agent.save_session", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await agent._execute_tool_call("write_file", {"path": "output"}, "pending")
        agent._dispatch_tool.assert_not_awaited()
        self.assertIsNone(agent._journal.lookup("pending"))

    async def test_restore_same_identity_replays_completed_result_without_dispatch(self):
        original = self.agent()
        original._openai_messages.append(tool_call())
        original._auto_save()
        original._journal.begin("pending", "write_file", {"path": "output", "content": "done"})
        original._journal.complete("pending", "file written once")
        restored = self.agent()
        restored._dispatch_tool = AsyncMock()
        restored.restore_session(session.load_session(original.session_id))
        self.assertEqual(restored.session_id, original.session_id)
        self.assertEqual(restored._openai_messages[-1], {
            "role": "tool", "tool_call_id": "pending", "content": "file written once",
        })
        restored._dispatch_tool.assert_not_awaited()
        with session_lease(restored.session_id):
            restored._auto_save()
        saved = session.load_session(original.session_id)
        self.assertEqual(saved["metadata"]["cwd"], str(Path.cwd()))
        self.assertEqual(saved["openaiMessages"][-1]["content"], "file written once")
        saved["metadata"]["cwd"] = str(self.root / "wrong-directory")
        with self.assertRaises(ValueError):
            self.agent().restore_session(saved)

    async def test_cancellation_marks_unknown_and_blocks_next_chat(self):
        agent = self.agent()
        agent._openai_messages.append(tool_call())
        agent._dispatch_tool = AsyncMock(side_effect=asyncio.CancelledError)
        with self.assertRaises(asyncio.CancelledError):
            await agent._execute_tool_call("write_file", {"path": "output"}, "pending")
        self.assertEqual(agent._journal.lookup("pending")["state"], "unknown")
        agent._chat_openai = AsyncMock()
        with self.assertRaises(UnknownExecution):
            await agent.chat("Try again using another tool call ID")
        agent._chat_openai.assert_not_awaited()

    async def test_never_started_call_gets_protocol_result_without_execution(self):
        agent = self.agent()
        agent._openai_messages.append(tool_call())
        agent._auto_save()
        restored = self.agent()
        restored._dispatch_tool = AsyncMock()
        restored.restore_session(session.load_session(agent.session_id))
        self.assertIn("Not executed", restored._openai_messages[-1]["content"])
        self.assertEqual(restored._journal.unresolved(), [])
        restored._dispatch_tool.assert_not_awaited()

    def test_session_lease_rejects_second_holder_and_releases(self):
        with session_lease("same"):
            with self.assertRaises(SessionBusy):
                with session_lease("same"):
                    self.fail("Second holder must not enter")
        with session_lease("same"):
            pass


if __name__ == "__main__":
    unittest.main()
