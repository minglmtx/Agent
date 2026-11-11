"""Offline-only, explicitly lossy Teacher page excerpts with simple references.

No caller imports this candidate by default. All attempts, messages, actions,
errors and feedback survive; only named public observation strings are excerpted.
Full source messages and line provenance remain in local diagnostic artifacts.
There is no dispatch, model, private evaluator, history window or codec recovery.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .actor_history_quotes import page_text, related_quotes
from .action_history import observed_targets
from .teacher_evidence_pages import PAGE_FIELDS, digest, serialized

VERSION = 'teacher-evidence-verbatim-quotes-v1'
GUIDE = '''
The final user JSON is an explicitly LOSSY page-excerpt candidate. All attempts,
ordered messages, submitted actions, errors, outcomes and structured feedback
remain present, including earlier revisions. An observation {"page_ref":"pN"}
means the plain text in shared_pages[pN]. Identical original pages share a record.
Pages marked excerpt=false retain their complete decoded source text. Pages
marked excerpt=true contain verbatim excerpts, not complete pages or summaries.
The candidate is explicitly lossy and has no recovery decoder. Omitted-line markers describe missing evidence; absence in an excerpt
is not proof that a control, fact or action was absent. Use each message's own
page reference for its transient element IDs. Historical pages are not current
state. Feedback is separate post-execution evidence: failed, unchecked and
unavailable checks are different, and no feedback implies a unique route.
A stored axtree_full_txt field may exceed the Actor request observation; this
format does not establish that the Actor saw every archived full-page line.
No page differences, node-ID arithmetic or omitted attempts need reconstruction.
'''


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _text_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _source_page(text, body=None):
    body = body or {}
    page = dict(observation=text, observation_mode=body.get('observation_mode'),
                observation_policy=body.get('observation_policy'))
    if any(line.startswith('@AX-ROWS-v1 ') for line in text.splitlines()):
        _require(page['observation_mode'] == 'full'
                 and page['observation_policy'] == 'full-lossless-rows-if-fits-v2',
                 'Packed AX requires explicit original full-mode/policy metadata')
    # The existing validated public selector expands only its declared lossless
    # row format. The Teacher receives plain quoted lines, never packed rows.
    expanded = page_text(page)
    return page, expanded


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON field; retain original message unchanged')
        value[key] = item
    return value


def _action_inventory(evidence):
    rows = []
    for i, attempt in enumerate(evidence['attempts']):
        for j, message in enumerate(attempt['trajectory']):
            if message.get('role') != 'assistant':
                continue
            action = message.get('action_payload')
            _require(message.get('action_kind') in (None, '') or isinstance(action, str),
                     'Recorded action_kind without string action_payload; unsupported source schema')
            _require(not any(message.get(k) for k in ('action', 'action_text')) or isinstance(action, str),
                     'Alternative action field requires explicit adapter; no silent empty targets')
            rows.append(dict(candidate_index=i, message_index=j, message_sha256=digest(message),
                action_field='action_payload', field_present='action_payload' in message,
                action_kind=message.get('action_kind'), payload_type=type(action).__name__,
                payload_sha256=_text_hash(action) if isinstance(action, str) else None))
    return rows


def _discover(evidence):
    _require(isinstance(evidence, dict) and isinstance(evidence.get('initial_observation'), str)
             and isinstance(evidence.get('attempts'), list), 'Raw structured Teacher evidence required')
    serialized(evidence)  # Reject nonfinite and non-JSON values without changing them.
    converted = deepcopy(evidence)
    records, by_value, fields, json_messages = [], {}, [], []

    def reference(text, path, body=None, action=None, previous=None):
        page, expanded = _source_page(text, body)
        # Exact raw page equality only. An interpretation difference must not
        # silently alias a differently decoded page with the same raw string.
        key = (text, expanded)
        if key not in by_value:
            by_value[key] = 'p' + str(len(records))
            records.append(dict(page_id=by_value[key], page=page, raw=text, expanded=expanded,
                                targets=[], previous=[], occurrences=[]))
        pid = by_value[key]; row = records[int(pid[1:])]
        context = dict(path=path, page_id=pid, raw_page_sha256=_text_hash(text),
                       expanded_page_sha256=_text_hash(expanded),
                       original_mode=page['observation_mode'], original_policy=page['observation_policy'])
        if isinstance(action, str):
            try:
                targets = observed_targets(action, dict(axtree_txt=expanded))
                context['target_selection'] = 'next_recorded_action_bid_matched_in_this_source_field'
                context['observed_target_count'] = len(targets)
            except (AttributeError, ValueError, SyntaxError, TypeError):
                targets = []
                context['target_selection'] = 'unparsed_action_preserved_without_inferred_target'
                context['observed_target_count'] = 0
            row['targets'].extend(t for t in targets if t not in row['targets'])
        else:
            context['target_selection'] = 'no_following_executed_action_payload'
            context['observed_target_count'] = 0
        if previous is not None and previous not in row['previous']:
            row['previous'].append(previous)
        row['occurrences'].append(context); fields.append(context)
        return dict(page_ref=pid)

    converted['initial_observation'] = reference(evidence['initial_observation'], ['initial_observation'])
    for i, attempt in enumerate(evidence['attempts']):
        _require(isinstance(attempt, dict) and isinstance(attempt.get('trajectory'), list), 'Every attempt needs its full trajectory')
        previous = {}
        for j, message in enumerate(attempt['trajectory']):
            _require(isinstance(message, dict) and isinstance(message.get('role'), str), 'Invalid trajectory message')
            content = message.get('content')
            if message['role'] != 'user' or not isinstance(content, str):
                continue
            try:
                body = json.loads(content, object_pairs_hook=_unique_object)
            except ValueError:
                continue
            if not isinstance(body, dict) or not any(isinstance(body.get(k), str) for k in PAGE_FIELDS):
                continue
            changed = deepcopy(body)
            following = attempt['trajectory'][j + 1] if j + 1 < len(attempt['trajectory']) else {}
            action = following.get('action_payload') if following.get('role') == 'assistant' else None
            base = ['attempts', i, 'trajectory', j, 'content']
            for key in PAGE_FIELDS:
                if not isinstance(body.get(key), str):
                    continue
                changed[key] = reference(body[key], base + [key], body, action, previous.get(key))
                previous[key] = _source_page(body[key], body)[0]
            converted['attempts'][i]['trajectory'][j]['content'] = changed
            json_messages.append(dict(path=base, original_content_sha256=_text_hash(content)))
    _action_inventory(evidence)
    return converted, records, fields, json_messages


def _excerpt(lines, indices):
    parts, previous = [], -1
    for index in indices:
        if index > previous + 1:
            parts.append('[Teacher excerpt: %d original lines omitted.]' % (index - previous - 1))
        parts.append(lines[index]); previous = index
    if previous + 1 < len(lines):
        parts.append('[Teacher excerpt: %d original lines omitted.]' % (len(lines) - previous - 1))
    return '\n'.join(parts)


def pack(evidence, *, page_token_counter, maximum_lines=32, maximum_full_page_tokens=8192):
    """Excerpt pages only; every actual target line survives the soft line limit.

    No six-step window or attempt filtering. Related public quotes choose lines;
    exact action-target lines across all occurrences are then required, even if
    this exceeds maximum_lines. Only the full-request budget may reject a result.
    """
    _require(type(maximum_lines) is int and maximum_lines > 0, 'Positive page line limit required')
    _require(type(maximum_full_page_tokens) is int and maximum_full_page_tokens > 0, 'Positive full-page token threshold required')
    converted, records, fields, json_messages = _discover(evidence)
    shared, audits = [], []
    for row in records:
        page_tokens = page_token_counter(row['expanded'])
        _require(type(page_tokens) is int and page_tokens >= 0, 'Actual page tokenizer count required')
        lines = row['expanded'].splitlines()
        excerpted = page_tokens > maximum_full_page_tokens
        if excerpted:
            _, selection = related_quotes(row['page'], targets=row['targets'], previous_pages=row['previous'], maximum_lines=maximum_lines)
            reasons = {r['index']: r['reason'] for r in selection['selected_lines']}
        else:
            reasons = {i: 'short_source_page_retained_in_full' for i in range(len(lines))}
        required = [i for i, line in enumerate(lines) if any(line.strip() == t['observed_node'] for t in row['targets'])]
        for i in required:
            reasons[i] = 'actual_action_target_required'
        indices = sorted(reasons)
        omitted = len(lines) - len(indices)
        shared.append(dict(page_id=row['page_id'], text=_excerpt(lines, indices) if excerpted else row['expanded'],
            observation_scope='Verbatim source-page excerpt, never a current-state assertion',
            excerpt=excerpted, omitted_lines=omitted, original_lines=len(lines)))
        audits.append(dict(page_id=row['page_id'], raw_page_sha256=_text_hash(row['raw']),
            expanded_page_sha256=_text_hash(row['expanded']), expanded_from_lossless_rows=row['raw'] != row['expanded'],
            selected_lines=[dict(index=i, reason=reasons[i]) for i in indices], original_lines=len(lines), omitted_lines=omitted,
            requested_maximum_lines=maximum_lines, required_target_lines=required,
            expanded_page_tokens=page_tokens, maximum_full_page_tokens=maximum_full_page_tokens,
            selection='related_quotes' if excerpted else 'complete_short_page',
            soft_limit_exceeded_for_actual_targets=excerpted and len(indices) > maximum_lines, occurrences=row['occurrences']))
    payload = dict(version=VERSION, lossy=True, reversible=False, shared_pages=shared, evidence=converted)
    audit = dict(version=VERSION, source_sha256=digest(evidence), payload_sha256=digest(payload),
        selection_policy='complete_short_pages_else_related_quotes_plus_all_observed_action_targets', maximum_lines=maximum_lines, maximum_full_page_tokens=maximum_full_page_tokens,
        pages=audits, page_fields=fields, json_messages=json_messages,
        attempts=[dict(index=i, source_sha256=digest(a), messages=len(a['trajectory'])) for i, a in enumerate(evidence['attempts'])],
        assistant_actions=_action_inventory(evidence),
        all_attempts_retained=True, all_messages_retained=True, non_page_values_retained=True,
        feedback_used_for_selection=False, private_evaluator_read=False, reversible=False,
        raw_evidence_location='raw-messages diagnostic artifact; source paths refer to its final user JSON')
    verify(evidence, payload, audit, page_token_counter=page_token_counter)
    return payload, audit


def verify(evidence, payload, audit, *, page_token_counter):
    """Check original non-page data and exact source-line provenance, not quality."""
    converted, records, fields, json_messages = _discover(evidence)
    _require(set(payload) == {'version', 'lossy', 'reversible', 'shared_pages', 'evidence'}, 'Unexpected model-facing field')
    _require(audit['assistant_actions'] == _action_inventory(evidence), 'Actual assistant/action field inventory changed')
    _require(audit['version'] == payload['version'] == VERSION and payload['lossy'] is True
             and payload['reversible'] is False and audit['reversible'] is False, 'Explicit lossy scope required')
    _require(audit['source_sha256'] == digest(evidence) and audit['payload_sha256'] == digest(payload), 'Source/payload identity changed')
    _require(payload['evidence'] == converted and audit['page_fields'] == fields and audit['json_messages'] == json_messages,
             'Attempt, message, feedback, non-page field or page source binding changed')
    _require(audit['attempts'] == [dict(index=i, source_sha256=digest(a), messages=len(a['trajectory'])) for i, a in enumerate(evidence['attempts'])],
             'Attempt coverage changed')
    _require(len(records) == len(payload['shared_pages']) == len(audit['pages']), 'Page coverage changed')
    for source, page, proof in zip(records, payload['shared_pages'], audit['pages']):
        _require(set(page) == {'page_id', 'text', 'observation_scope', 'excerpt', 'omitted_lines', 'original_lines'}, 'Unexpected page field')
        _require(page['observation_scope'] == 'Verbatim source-page excerpt, never a current-state assertion', 'Page scope changed')
        lines = source['expanded'].splitlines(); indices = [r['index'] for r in proof['selected_lines']]
        _require(source['page_id'] == page['page_id'] == proof['page_id'] and proof['occurrences'] == source['occurrences'], 'Page identity/source mismatch')
        _require(all(type(i) is int and 0 <= i < len(lines) for i in indices) and indices == sorted(set(indices)), 'Invalid quoted source lines')
        required = [i for i, line in enumerate(lines) if any(line.strip() == t['observed_node'] for t in source['targets'])]
        _require(proof['required_target_lines'] == required and set(required) <= set(indices), 'Actual action target omitted')
        _require(proof['raw_page_sha256'] == _text_hash(source['raw']) and proof['expanded_page_sha256'] == _text_hash(source['expanded']), 'Page bytes changed')
        page_tokens = page_token_counter(source['expanded'])
        excerpted = page_tokens > audit['maximum_full_page_tokens']
        _require(proof['expanded_page_tokens'] == page_tokens and proof['maximum_full_page_tokens'] == audit['maximum_full_page_tokens'], 'Page tokenizer count changed')
        _require(excerpted or indices == list(range(len(lines))), 'Short complete page was truncated')
        _require(page['text'] == (_excerpt(lines, indices) if excerpted else source['expanded']) and page['excerpt'] is excerpted
                 and page['original_lines'] == proof['original_lines'] == len(lines)
                 and page['omitted_lines'] == proof['omitted_lines'] == len(lines) - len(indices), 'Non-verbatim quote or omitted count mismatch')
    return True


def _persist_many(path, artifacts):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    files = [(path.with_name(path.stem + '-' + name + '.json'), json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n') for name, value in artifacts.items()]
    for target, text in files:
        _require(not target.exists() or target.read_text() == text, 'Teacher diagnostic checkpoint changed: ' + target.name)
    for target, text in files:
        if not target.exists():
            with target.open('x') as stream:
                stream.write(text)


def prepare(messages, tokenizer, maximum, *, diagnostic_path, allow_lossy=False, maximum_lines=32, maximum_full_page_tokens=8192):
    """Offline opt-in only; count the complete actual-template candidate request.

    Raw and derived messages/audit are saved even on overflow. No fallback that
    changes lines, attempts, budget, encoding, window, model or Teacher rounds.
    Fits is only a token-size fact; dispatch/admission remain explicitly false.
    """
    _require(allow_lossy is True, 'Lossy Teacher candidate is disabled; explicit offline opt-in required')
    _require(type(maximum) is int and maximum > 0, 'Positive input-token budget required')
    _require(isinstance(messages, list) and len(messages) >= 2 and messages[0].get('role') == 'system'
             and isinstance(messages[0].get('content'), str) and messages[-1].get('role') == 'user'
             and isinstance(messages[-1].get('content'), str), 'Original Teacher request messages required')
    artifacts = dict(raw_messages=deepcopy(messages)); report = dict(version=VERSION, production_admitted=False,
        teacher_comprehension_validated=False, dispatch_authorized=False, model_calls=0, api_calls=0,
        explicit_lossy=True, reversible=False, maximum=maximum, maximum_lines=maximum_lines,
        maximum_full_page_tokens=maximum_full_page_tokens,
        raw_messages_sha256=digest(messages), fits=False)
    try:
        evidence = json.loads(messages[-1]['content'], object_pairs_hook=_unique_object)
        token_cache = {}
        def page_tokens(text):
            key = _text_hash(text)
            if key not in token_cache:
                token_cache[key] = len(tokenizer.encode(text, add_special_tokens=False))
            return token_cache[key]
        payload, audit = pack(evidence, page_token_counter=page_tokens, maximum_lines=maximum_lines, maximum_full_page_tokens=maximum_full_page_tokens)
        candidate = deepcopy(messages); candidate[0]['content'] += GUIDE; candidate[-1]['content'] = serialized(payload)
        artifacts.update(payload=payload, audit=audit, candidate_messages=candidate)
        count = lambda value: len(tokenizer.apply_chat_template(value, tokenize=True, add_generation_prompt=True, enable_thinking=False))
        raw_tokens, candidate_tokens = count(messages), count(candidate)
        part = lambda value: len(tokenizer.encode(serialized(value), add_special_tokens=False))
        report.update(status='fits' if candidate_tokens <= maximum else 'over_budget', raw_tokens=raw_tokens,
            selected_tokens=candidate_tokens, candidate_tokens=candidate_tokens, fits=candidate_tokens <= maximum,
            selected_encoding=VERSION, source_sha256=digest(evidence), candidate_messages_sha256=digest(candidate),
            candidate_component_tokens={k: part(v) for k, v in payload.items()},
            raw_component_tokens={k: part(v) for k, v in evidence.items()},
            component_tokens_include_no_chat_template=True, component_tokens_are_not_additive=True,
            attempt_count=len(evidence['attempts']), message_counts=[len(a['trajectory']) for a in evidence['attempts']],
            shared_page_count=len(payload['shared_pages']), all_attempts_and_messages_retained=True,
            excerpted_page_count=sum(p['excerpt'] for p in payload['shared_pages']),
            actual_omitted_lines=sum(p['omitted_lines'] for p in payload['shared_pages']))
    except Exception as exc:
        report.update(status='candidate_error', error=dict(type=type(exc).__name__, message=str(exc)))
        artifacts['diagnostic'] = report; _persist_many(diagnostic_path, artifacts)
        raise
    artifacts['diagnostic'] = report; _persist_many(diagnostic_path, artifacts)
    if not report['fits']:
        raise ValueError('Lossy Teacher candidate requires %d tokens; budget %d; full diagnostics saved; dispatch denied' % (candidate_tokens, maximum))
    return candidate, report
