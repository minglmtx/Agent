"""Bounded, lossless readable Teacher inputs; isolated candidate, not admitted.

The page payload keeps its original teacher-evidence-pages-v2 marker. This
module's VERSION identifies the added metadata/step references in the recovery
sidecar and diagnostic; GUIDE describes them to the Teacher. No private
reference, task-specific filtering, new budget or model invocation occurs here.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from . import teacher_evidence_pages as pages

VERSION = 'teacher-evidence-readable-steps-v1'
METADATA_VERSION = 'teacher-observation-metadata-v1'
BASE_WINDOW = 32
DEPTH_COST = 128
ERROR_FIELDS = ('last_action_error', 'action_execution_error')
TIMELINE_COLUMNS = ('response_index', 'message_index', 'submitted_action', 'functions',
                    'before_page', 'after_page', 'observed_targets', 'observed_error_after',
                    'action_success_inferred')
GUIDE = '''
The additional typed references only share exact duplicated values.
observation_metadata rows give a field and its exact value; {"metadata_ref":"mN"}
in an observation means that value at that field in that step.
shared_steps preserves every original assistant message and its timeline row once.
In evidence.trajectory, {"assistant_step_ref":"aImJ"} means shared_steps' assistant_message.
An index timeline {"steps_ref":[...]} means those shared_steps' timeline rows in order.
When steps use timeline_values, timeline_columns names its fields in the same order.
The original action remains directly in assistant_message.action_payload, model
response in assistant_message.content, and each exact following error in the
step's timeline observed_error_after column. {"step_error_ref":"aImJ"} in an
observation means that step's exact observed_error_after. Empty errors remain empty.
Read the ordered steps, action, target lines, before/after page and error together;
all candidate outcomes and evaluator feedback remain directly in evidence.attempts.
These are shared values, not omitted observations or a claim of action success.
'''


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _keys(value, expected, label):
    _require(isinstance(value, dict) and set(value) == set(expected), 'Invalid ' + label)


def _index(value, size, label):
    _require(type(value) is int and 0 <= value < size, 'Invalid ' + label)
    return value


def _validate_evidence(evidence):
    _require(isinstance(evidence, dict) and isinstance(evidence.get('initial_observation'), str)
             and isinstance(evidence.get('attempts'), list), 'Structured Teacher evidence required')
    for attempt in evidence['attempts']:
        _require(isinstance(attempt, dict) and isinstance(attempt.get('trajectory'), list), 'Invalid trajectory')
        for message in attempt['trajectory']:
            _require(isinstance(message, dict) and isinstance(message.get('role'), str), 'Invalid trajectory message')
    pages.serialized(evidence)  # Reject non-JSON and nonfinite values before encoding.


def _pack_pages(evidence):
    converted = deepcopy(evidence)
    records, texts, depths, fields, styles = [], [], [], [], []
    seen = {}

    def reference(text, path):
        if text not in seen:
            pid = 'p' + str(len(records))
            row, depth = dict(page_id=pid, text=text), 0
            # At most 32 comparisons per new page; never an unbounded all-pairs search.
            for base in range(max(0, len(records) - BASE_WINDOW), len(records)):
                if depths[base] >= 4:
                    continue
                candidate = dict(page_id=pid, base_page=records[base]['page_id'],
                                 segments=pages._segments(texts[base], text))
                if (len(pages.serialized(candidate)) + DEPTH_COST * (depths[base] + 1)
                        < len(pages.serialized(row)) + DEPTH_COST * depth):
                    row, depth = candidate, depths[base] + 1
            seen[text] = pid
            records.append(row)
            texts.append(text)
            depths.append(depth)
        fields.append(path)
        return dict(page_ref=seen[text])

    converted['initial_observation'] = reference(evidence['initial_observation'], ['initial_observation'])
    for i, attempt in enumerate(converted['attempts']):
        for j, message in enumerate(attempt['trajectory']):
            content = message.get('content')
            if message.get('role') != 'user' or not isinstance(content, str):
                continue
            try:
                body = json.loads(content)
            except ValueError:
                continue
            if not isinstance(body, dict):
                continue
            style = pages.json_style(content, body)
            if style is None:
                continue
            path = ['attempts', i, 'trajectory', j, 'content']
            styles.append(dict(path=path, **style))
            for key in pages.PAGE_FIELDS:
                if isinstance(body.get(key), str):
                    body[key] = reference(body[key], path + [key])
            message['content'] = body
    payload = dict(version=pages.VERSION, readable_index=pages.readable_index(evidence, seen),
                   shared_pages=records, evidence=converted)
    recovery = dict(version=pages.VERSION, source_sha256=pages.digest(evidence),
                    payload_sha256=pages.digest(payload), page_fields=fields, json_text_styles=styles,
                    page_sha256=[hashlib.sha256(text.encode()).hexdigest() for text in texts])
    return payload, recovery


def _metadata(payload, recovery):
    value = deepcopy(payload)
    found, bindings, rows = {}, [], []
    for i, attempt in enumerate(value['evidence']['attempts']):
        for j, message in enumerate(attempt['trajectory']):
            body = message.get('content')
            if message.get('role') != 'user' or not isinstance(body, dict):
                continue
            for key, item in body.items():
                if key in pages.PAGE_FIELDS or key in ERROR_FIELDS:
                    continue
                text = pages.serialized(item)
                if len(text) >= 24:
                    found.setdefault((key, text), []).append(['evidence', 'attempts', i, 'trajectory', j, 'content', key])
    for (key, text), paths in found.items():
        if len(paths) < 2:
            continue
        mid = 'm' + str(len(rows))
        ref = dict(metadata_ref=mid)
        row = dict(metadata_id=mid, field=key, value=json.loads(text))
        if len(pages.serialized(row)) + len(paths) * len(pages.serialized(ref)) >= len(paths) * len(text):
            continue
        rows.append(row)
        for path in paths:
            obj = value
            for part in path[:-1]:
                obj = obj[part]
            obj[path[-1]] = deepcopy(ref)
            bindings.append(dict(path=path, metadata_id=mid))
    value['observation_metadata'] = rows
    return value, dict(version=METADATA_VERSION, base_recovery=recovery, metadata_fields=bindings,
                       payload_sha256=pages.digest(value))


def pack(evidence):
    """Return full readable payload and sidecar; fixed 32 bases/cost 128/depth 4."""
    _validate_evidence(evidence)
    payload, recovery = _pack_pages(evidence)
    value, metadata_recovery = _metadata(payload, recovery)
    steps, errors, columns = [], [], None
    for i, index in enumerate(value['readable_index']['attempts']):
        trajectory, ids = value['evidence']['attempts'][i]['trajectory'], []
        for row in index['timeline']:
            j = row['message_index']
            sid = 'a' + str(i) + 'm' + str(j)
            ids.append(sid)
            message = trajectory[j]
            _require(message['role'] == 'assistant' and message.get('action_payload') == row['submitted_action'],
                     'Timeline differs from assistant message')
            if columns is None:
                columns = list(row)
            _require(list(row) == columns == list(TIMELINE_COLUMNS), 'Unexpected timeline fields')
            steps.append(dict(step_id=sid, assistant_message=message,
                              timeline_values=[row[key] for key in columns]))
            trajectory[j] = dict(assistant_step_ref=sid)
            if j + 1 < len(trajectory):
                next_message = trajectory[j + 1]
                body = next_message.get('content')
                if next_message.get('role') == 'user' and isinstance(body, dict):
                    for key in ERROR_FIELDS:
                        ref = dict(step_error_ref=sid)
                        if (key in body and body[key] == row['observed_error_after']
                                and len(pages.serialized(ref)) < len(pages.serialized(body[key]))):
                            body[key] = ref
                            errors.append(dict(candidate=i, message=j + 1, field=key, step_id=sid))
        index['timeline'] = dict(steps_ref=ids)
    value['shared_steps'], value['timeline_columns'] = steps, columns or []
    side = dict(version=VERSION, base_recovery=metadata_recovery, error_fields=errors,
                payload_sha256=pages.digest(value))
    _require(unpack(value, side) == evidence, 'Readable Teacher evidence changed')
    return value, side


def _restore(payload, recovery):
    _keys(recovery, ('version', 'base_recovery', 'error_fields', 'payload_sha256'), 'step recovery')
    _require(recovery['version'] == VERSION and pages.digest(payload) == recovery['payload_sha256'],
             'Readable Teacher payload identity changed')
    _keys(payload, ('version', 'readable_index', 'shared_pages', 'evidence', 'observation_metadata',
                    'shared_steps', 'timeline_columns'), 'readable payload')
    _require(payload['version'] == pages.VERSION, 'Unknown underlying page version')
    value = deepcopy(payload)
    steps, columns = value.pop('shared_steps'), value.pop('timeline_columns')
    _require(isinstance(steps, list) and columns == (list(TIMELINE_COLUMNS) if steps else []),
             'Invalid timeline columns')
    by_id = {}
    for step in steps:
        _keys(step, ('step_id', 'assistant_message', 'timeline_values'), 'shared step')
        sid, message, fields = step['step_id'], step['assistant_message'], step['timeline_values']
        _require(isinstance(sid, str) and sid not in by_id and isinstance(message, dict)
                 and message.get('role') == 'assistant' and isinstance(fields, list)
                 and len(fields) == len(columns), 'Invalid shared assistant message')
        by_id[sid] = dict(message=message, timeline=dict(zip(columns, fields)))
    attempts = value['evidence']['attempts']
    index_attempts = value['readable_index']['attempts']
    _require(isinstance(attempts, list) and isinstance(index_attempts, list)
             and len(attempts) == len(index_attempts), 'Attempt/index mismatch')
    used = []
    for i, index in enumerate(index_attempts):
        _require(type(index['candidate_index']) is int and index['candidate_index'] == i, 'Wrong indexed candidate')
        _keys(index['timeline'], ('steps_ref',), 'timeline references')
        ids, trajectory, rows = index['timeline']['steps_ref'], attempts[i]['trajectory'], []
        _require(isinstance(ids, list) and isinstance(trajectory, list), 'Invalid step list')
        previous = -1
        for ordinal, sid in enumerate(ids):
            _require(isinstance(sid, str) and sid in by_id and sid not in used, 'Foreign/duplicate step')
            step = by_id[sid]
            row = step['timeline']
            j = _index(row['message_index'], len(trajectory), 'message index')
            _require(j > previous and type(row['response_index']) is int and row['response_index'] == ordinal
                     and row['action_success_inferred'] is False
                     and sid == 'a' + str(i) + 'm' + str(j)
                     and trajectory[j] == dict(assistant_step_ref=sid), 'Step source/order mismatch')
            _require(step['message'].get('action_payload') == row['submitted_action'], 'Step action changed')
            trajectory[j] = step['message']
            rows.append(row)
            used.append(sid)
            previous = j
        index['timeline'] = rows
    _require(used == [step['step_id'] for step in steps], 'Unreferenced/out-of-order shared step')
    _require(isinstance(recovery['error_fields'], list), 'Invalid error bindings')
    seen = set()
    for binding in recovery['error_fields']:
        _keys(binding, ('candidate', 'message', 'field', 'step_id'), 'error binding')
        i = _index(binding['candidate'], len(attempts), 'error candidate')
        j = _index(binding['message'], len(attempts[i]['trajectory']), 'error message')
        key, sid = binding['field'], binding['step_id']
        _require(key in ERROR_FIELDS and (i, j, key) not in seen
                 and sid == 'a' + str(i) + 'm' + str(j - 1) and sid in by_id, 'Wrong error owner')
        message = attempts[i]['trajectory'][j]
        _require(message.get('role') == 'user' and isinstance(message.get('content'), dict), 'Error outside observation')
        body = message['content']
        _require(body.get(key) == dict(step_error_ref=sid), 'Error reference changed')
        body[key] = deepcopy(by_id[sid]['timeline']['observed_error_after'])
        seen.add((i, j, key))
    side = recovery['base_recovery']
    _keys(side, ('version', 'base_recovery', 'metadata_fields', 'payload_sha256'), 'metadata recovery')
    _require(side['version'] == METADATA_VERSION and pages.digest(value) == side['payload_sha256'],
             'Restored step structure changed')
    rows = value.pop('observation_metadata')
    _require(isinstance(rows, list) and isinstance(side['metadata_fields'], list), 'Invalid metadata rows')
    by_meta = {}
    for i, row in enumerate(rows):
        _keys(row, ('metadata_id', 'field', 'value'), 'metadata row')
        _require(row['metadata_id'] == 'm' + str(i) and isinstance(row['field'], str)
                 and row['field'] not in pages.PAGE_FIELDS + ERROR_FIELDS, 'Invalid metadata field')
        by_meta[row['metadata_id']] = row
    seen, used_meta = set(), set()
    for binding in side['metadata_fields']:
        _keys(binding, ('path', 'metadata_id'), 'metadata binding')
        path = binding['path']
        _require(isinstance(path, list) and len(path) == 7 and path[:2] == ['evidence', 'attempts']
                 and path[3] == 'trajectory' and path[5] == 'content' and isinstance(path[6], str),
                 'Metadata binding outside observation')
        i = _index(path[2], len(attempts), 'metadata candidate')
        j = _index(path[4], len(attempts[i]['trajectory']), 'metadata message')
        mid = binding['metadata_id']
        _require(isinstance(mid, str) and mid in by_meta and tuple(path) not in seen, 'Duplicate/foreign metadata reference')
        row, message = by_meta[mid], attempts[i]['trajectory'][j]
        _require(message.get('role') == 'user' and isinstance(message.get('content'), dict), 'Metadata outside user observation')
        body = message['content']
        _require(path[-1] == row['field'] and body.get(path[-1]) == dict(metadata_ref=mid), 'Metadata reference changed')
        body[path[-1]] = deepcopy(row['value'])
        seen.add(tuple(path))
        used_meta.add(mid)
    _require(used_meta == set(by_meta), 'Unreferenced metadata row')
    return pages.unpack(value, side['base_recovery'])


def unpack(payload, recovery):
    """Strict structural/digest/page/index validation; never relies on assert."""
    try:
        return _restore(payload, recovery)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError('Invalid readable Teacher evidence: ' + str(exc)) from exc


def _persist(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if path.exists():
        _require(path.read_text() == text, 'Teacher diagnostic checkpoint changed: ' + path.name)
    else:
        with path.open('x') as stream:
            stream.write(text)


def prepare(messages, tokenizer, maximum, *, diagnostic_path):
    """Choose shortest raw/old-pages/readable-steps input using actual tokenizer.

    All three representations stay exact. Save candidate payload/recovery and
    token diagnostics before raising for overflow. Same-path changes refuse to
    overwrite historical evidence. This function never sends a model request.
    """
    _require(type(maximum) is int and maximum > 0, 'Positive input budget required')
    _require(isinstance(messages, list) and len(messages) >= 2
             and isinstance(messages[0], dict) and messages[0].get('role') == 'system'
             and isinstance(messages[0].get('content'), str)
             and isinstance(messages[-1], dict) and messages[-1].get('role') == 'user'
             and isinstance(messages[-1].get('content'), str), 'Teacher system and final evidence message required')
    evidence = json.loads(messages[-1]['content'])
    _validate_evidence(evidence)
    old_payload, old_recovery = pages.pack(evidence)
    _require(pages.unpack(old_payload, old_recovery) == evidence, 'Original page evidence changed')
    payload, recovery = pack(evidence)
    old_messages, new_messages = deepcopy(messages), deepcopy(messages)
    old_messages[0]['content'] += pages.GUIDE
    old_messages[-1]['content'] = pages.serialized(old_payload)
    new_messages[0]['content'] += pages.GUIDE + GUIDE
    new_messages[-1]['content'] = pages.serialized(payload)
    representations = [('original', messages), (pages.VERSION, old_messages), (VERSION, new_messages)]
    counts = {name: len(tokenizer.apply_chat_template(value, tokenize=True, add_generation_prompt=True,
                                                     enable_thinking=False)) for name, value in representations}
    name, selected = min(representations, key=lambda item: counts[item[0]])
    part_tokens = lambda value: len(tokenizer.encode(pages.serialized(value), add_special_tokens=False))
    report = dict(version=VERSION, source_sha256=pages.digest(evidence), raw_tokens=counts['original'],
        encoded_tokens=counts[VERSION], old_encoded_tokens=counts[pages.VERSION], candidate_tokens=counts,
        selected_tokens=counts[name], maximum=maximum, fits=counts[name] <= maximum, exact_round_trip=True,
        selected_encoding=name, raw_component_tokens={k: part_tokens(v) for k, v in evidence.items()},
        readable_component_tokens={k: part_tokens(v) for k, v in payload.items()},
        component_tokens_include_no_chat_template=True, component_tokens_are_not_additive=True,
        shared_page_count=len(payload['shared_pages']), attempt_count=len(evidence['attempts']),
        base_window=BASE_WINDOW, depth_cost=DEPTH_COST, maximum_page_depth=4,
        teacher_comprehension_validated=False, production_admitted=False)
    path = Path(diagnostic_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for suffix, value in [('payload', payload), ('recovery', recovery), ('old-payload', old_payload),
                          ('old-recovery', old_recovery), ('raw-messages', messages),
                          ('selected-messages', selected), ('diagnostic', report)]:
        _persist(path.with_name(path.stem + '-' + suffix + '.json'), value)
    if not report['fits']:
        raise ValueError('Teacher evidence requires %d tokens; budget %d; full diagnostics saved' % (counts[name], maximum))
    return selected, report
