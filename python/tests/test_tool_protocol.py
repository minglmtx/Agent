from copy import deepcopy
import unittest
from mini_claude.tool_protocol import project_history

def history(args='{bad', mixed=False):
    calls = [{'id': 'bad', 'type': 'function', 'function': {'name': 'write_file', 'arguments': args}}]
    results = [{'role': 'tool', 'tool_call_id': 'bad', 'content': 'Invalid tool arguments; not executed'}]
    if mixed:
        calls.append({'id': 'good', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{"file_path":"answer.py"}'}})
        results.insert(0, {'role': 'tool', 'tool_call_id': 'good', 'content': 'def add(a,b): return 0'})
    return [{'role': 'user', 'content': 'Implement add'}, {'role': 'assistant', 'content': None, 'tool_calls': calls}, *results]


class ProjectionTests(unittest.TestCase):
    def test_valid_no_change(self):
        original = history('{}')
        self.assertEqual(project_history(original), (original, []))
    def test_invalid_not_mutated(self):
        original = history(); before = deepcopy(original)
        projected, events = project_history(original)
        self.assertEqual(original, before)
        self.assertEqual(events[0]['raw_call']['function']['arguments'], '{bad')
        self.assertFalse(any(m.get('tool_calls') for m in projected))
        self.assertIn('not executed', projected[-1]['content'])
    def test_mixed_pairs(self):
        original = history(mixed=True)
        projected, events = project_history(original)
        self.assertEqual(projected[1]['tool_calls'], [original[1]['tool_calls'][1]])
        self.assertEqual(projected[2], original[2])
        self.assertEqual(len(events), 1)
    def test_missing_result_rejected(self):
        with self.assertRaisesRegex(ValueError, 'paired'):
            project_history(history()[:-1])
    def test_duplicate_result_rejected(self):
        h = history()
        with self.assertRaises(ValueError): project_history(h+[h[-1]])
    def test_duplicate_identity_rejected(self):
        h = history();h[1]['tool_calls'] *= 2
        with self.assertRaises(ValueError): project_history(h)
    def test_json_wrong_shapes(self):
        for args in ['[]', 'null', '"hello"', '1', '{"x":"unterminated', '{"x":"literal\nnewline"}']:
            with self.subTest(args=args):
                projected, events = project_history(history(args))
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]['raw_call']['function']['arguments'], args)
    def test_idempotent(self):
        projected, _ = project_history(history(mixed=True))
        self.assertEqual(project_history(projected), (projected, []))


if __name__ == '__main__':
    unittest.main()
