import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from mini_claude.agent import Agent
from mini_claude import session


class StopReasonTests(unittest.IsolatedAsyncioTestCase):
    async def run_mock(self, message, limit=0):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "MINI_CLAUDE_STATE_DIR": tmp, "MINI_CLAUDE_DISABLE_MEMORY": "1",
        }), patch.object(session, "SESSION_DIR", Path(tmp) / "sessions"):
            agent = Agent(api_base="http://127.0.0.1:1/v1", api_key="local",
                          model="test", custom_system_prompt="Test",
                          is_sub_agent=True, max_turns=limit)
            agent._call_openai_stream = AsyncMock(return_value={
                "choices": [{"message": message}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            })
            agent._dispatch_tool = AsyncMock(return_value="should not run")
            try:
                result = await agent.run_once("test")
                agent._dispatch_tool.assert_not_awaited()
                return result, session.load_session(agent.session_id)
            finally:
                await agent.close()

    async def test_budget_stop_is_not_model_finish(self):
        result, saved = await self.run_mock({
            "role": "assistant", "content": None, "tool_calls": [{
                "id": "first", "type": "function",
                "function": {"name": "read_file", "arguments": '{"file_path":"a"}'},
            }],
        })
        self.assertEqual(result["stop_reason"], "turn_limit")
        self.assertEqual(saved["stop_reason"], "turn_limit")
        self.assertIn("not executed", saved["openaiMessages"][-1]["content"])

    async def test_model_finish_does_not_imply_evaluation_success(self):
        result, saved = await self.run_mock({"role": "assistant", "content": "Done", "tool_calls": None})
        self.assertEqual(result["stop_reason"], "model_finished")
        self.assertNotIn("success", result)


if __name__ == "__main__":
    unittest.main()
