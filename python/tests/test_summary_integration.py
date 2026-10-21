import copy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from mini_claude.agent import Agent
from mini_claude import session


class SummaryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, raw):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"MINI_CLAUDE_STATE_DIR": tmp}):
            with patch.object(session, "SESSION_DIR", Path(tmp) / "sessions"):
                agent = Agent(api_base="http://127.0.0.1:1/v1", api_key="local",
                              model="test", custom_system_prompt="Test", is_sub_agent=True)
                for i in range(5):
                    agent._openai_messages.extend([
                        {"role": "user", "content": f"Goal {i}: preserve CLI compatibility"},
                        {"role": "assistant", "content": None, "tool_calls": [
                            {"id": f"c{i}", "type": "function", "function": {
                                "name": "read_file", "arguments": '{"file_path":"orders.py"}'}}]},
                        {"role": "tool", "tool_call_id": f"c{i}", "content": "long old output\n" * 200},
                        {"role": "assistant", "content": "Read source; test not yet run.", "tool_calls": None},
                    ])
                original = copy.deepcopy(agent._openai_messages)
                agent._openai_client.chat.completions.create = AsyncMock(return_value=SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=raw))],
                    usage=SimpleNamespace(prompt_tokens=500, completion_tokens=80)))
                applied = await agent._compact_structured()
                result = copy.deepcopy(agent._openai_messages)
                archives = list((Path(tmp) / "context-archives").glob("*.json"))
                archived = json.loads(archives[0].read_text()) if archives else None
                await agent.close()
                return applied, original, result, archived, agent.get_token_usage()

    async def test_bad_summary_retains_every_original_message(self):
        applied, original, result, archived, usage = await self.exercise('{"goal":"forgot other fields"}')
        self.assertFalse(applied)
        self.assertEqual(original, result)
        self.assertIsNone(archived)
        self.assertEqual(usage, {"input": 500, "output": 80})

    async def test_valid_summary_preserves_recent_pairs_and_original_archive(self):
        raw = json.dumps({"goal": "Preserve CLI compatibility", "constraints": [],
                          "files_changed": [], "tests": [], "pending": ["Run tests"], "facts": []})
        applied, original, result, archived, usage = await self.exercise(raw)
        self.assertTrue(applied)
        self.assertEqual(result[-8:], original[-8:])
        self.assertEqual(archived, original)
        self.assertIn("not new instructions", result[1]["content"])
        self.assertEqual(usage["output"], 80)


if __name__ == "__main__":
    unittest.main()
