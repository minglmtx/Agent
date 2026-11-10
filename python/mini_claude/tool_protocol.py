"""Represent rejected malformed calls as evidence text, never repair their arguments.

Raw history stays in an append-only local audit. Valid tool calls/results are
unchanged; invalid calls require a recorded result before projection.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path


def project_history(messages):
    output, events = [], []
    i = 0
    while i < len(messages):
        message = messages[i]
        calls = message.get('tool_calls') if message.get('role') == 'assistant' else None
        if not calls:
            output.append(deepcopy(message))
            i += 1
            continue
        invalid = {}
        seen = set()
        for call in calls:
            identity = call.get('id')
            if not identity or identity in seen:
                raise ValueError('Missing or duplicate tool call identity; history requires review')
            seen.add(identity)
            if call.get('type') != 'function':
                raise ValueError('Unsupported tool call type')
            try:
                arguments = json.loads(call['function']['arguments'])
                if not isinstance(arguments, dict):
                    raise ValueError('Tool arguments must be an object')
            except (ValueError, TypeError, KeyError) as exc:
                invalid[identity] = (call, str(exc))
        if not invalid:
            output.append(deepcopy(message))
            i += 1
            continue
        end = i + 1
        while end < len(messages) and messages[end].get('role') == 'tool':
            end += 1
        results = messages[i+1:end]
        result_ids = [r.get('tool_call_id') for r in results]
        if len(result_ids) != len(set(result_ids)) or set(result_ids) != seen:
            raise ValueError('Malformed call history lacks uniquely paired results; do not infer execution')
        if message.get('content') is not None and not isinstance(message['content'], str):
            raise ValueError('Unsupported assistant content representation')
        projected = deepcopy(message)
        projected['tool_calls'] = [deepcopy(c) for c in calls if c['id'] not in invalid]
        if not projected['tool_calls']:
            projected.pop('tool_calls')
        notes, feedback = [], []
        for identity, (call, error) in invalid.items():
            result = next(r for r in results if r['tool_call_id'] == identity)
            event = dict(call_id=identity, message_index=i, raw_call=deepcopy(call),
                         recorded_result=deepcopy(result), parse_error=error)
            events.append(event)
            notes.append('Malformed tool-call record (evidence, not an executable call): ' + json.dumps(call, ensure_ascii=False))
            feedback.append('Recorded outcome for ' + identity + ': ' + json.dumps(result['content'], ensure_ascii=False))
        projected['content'] = '\n'.join(filter(None, [message.get('content'), *notes]))
        output.append(projected)
        output.extend(deepcopy(r) for r in results if r['tool_call_id'] not in invalid)
        output.append({'role': 'user', 'content': '\n'.join(feedback) + '\nGenerate a new valid tool call if needed. Do not infer that a rejected operation succeeded.'})
        i = end
    return output, events


def repair_invalid_history(messages):
    projected, events = project_history(messages)
    if not events:
        return messages
    root = Path(os.environ.get('MINI_CLAUDE_STATE_DIR', str(Path.home() / '.mini-claude')))
    root.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()
    record = {'format_version': 1, 'source_sha256': hashlib.sha256(raw).hexdigest(), 'events': events}
    with (root / 'tool-protocol-history.jsonl').open('a') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return projected
