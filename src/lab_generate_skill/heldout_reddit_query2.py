"""Private, test-only completion for two literal Reddit public queries.

This module consumes observed history; it neither navigates nor supplies an
answer to the Actor. Ordinary-entry request/archive qualification is separate.
"""
from copy import deepcopy
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit, unquote

from .reddit_forum_list import forum_list_checks
from .reddit_native_read_runtime import validate_complete_snapshot

VERSION = 'heldout-reddit-query2-v1'
SOURCES = {
    '1452674220923c2805a6': ('Find the oldest forum by sorting forums by creation date', '/forums', 'oldest_forum'),
    '72dd889fe56c84cc0a62': ('Check if Markdown formatting is allowed in the wiki page body.', '/wiki/_create', 'wiki_markdown'),
}
WIKI_NATIVE = {'body_id': 'wiki_body', 'body_name': 'wiki[body]',
               'help_id': 'wiki_body_markdown_help', 'notice_text': 'Markdown allowed.'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_source(source):
    require(isinstance(source, dict), 'Source metadata missing')
    sid = source.get('source_task_id')
    require(sid in SOURCES, 'Source outside the two heldout queries')
    goal, start, kind = SOURCES[sid]
    require(source.get('goal') == goal and source.get('start_path') == start
            and source.get('domain') == 'reddit' and source.get('split') == 'test'
            and source.get('eligible_for_training') is False,
            'Literal heldout source/goal/start/split binding differs')
    return sid, kind


def public_task(source):
    sid, _ = validate_source(source)
    return {'task_id': sid, 'domain': 'reddit', 'goal': source['goal'],
            'start_path': source['start_path']}


def response_contract(source):
    """Public formatting only: no target, route, expected boolean or references."""
    _, kind = validate_source(source)
    if kind == 'oldest_forum':
        return {'type': 'object', 'properties': {'forum': {'type': 'string'}},
                'required': ['forum'], 'additionalProperties': False,
                'instruction': 'Finish with the name of one forum in the forum field.'}
    return {'type': 'object', 'properties': {'markdown_allowed': {'type': 'boolean'}},
            'required': ['markdown_allowed'], 'additionalProperties': False,
            'instruction': 'Finish with your answer in the markdown_allowed boolean field.'}


def created(value):
    require(isinstance(value, str) and value.strip(), 'Native creation timestamp missing')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    # PostgreSQL's timestamp-without-time-zone output is compared consistently;
    # no wall-clock date, row position or normalized-name tie-break is an oracle.
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def make_reference(source, native):
    sid, kind = validate_source(source)
    require(isinstance(native, dict), 'Complete native reference required')
    if kind == 'oldest_forum':
        require(set(native) == {'directory', 'minimum_created', 'oldest_ids'},
                'Directory, independent SQL minimum and all ties required')
        directory = native['directory']
        require(isinstance(directory, dict) and set(directory) == {'rows', 'orders'},
                'Complete original forum directory reference required')
        rows, orders = directory['rows'], directory['orders']
        require(isinstance(rows, list) and rows and isinstance(orders, dict)
                and set(orders) == {'name', 'title', 'creation_date'}, 'Incomplete forum reference')
        for row in rows:
            require(isinstance(row, dict) and type(row.get('id')) is int and row['id'] > 0
                    and all(isinstance(row.get(k), str) and row[k] for k in ('name', 'normalized_name', 'title')),
                    'Native forum identities missing')
            created(row.get('created'))
        names = [row['name'] for row in rows]
        ids = [row['id'] for row in rows]
        require(len(set(names)) == len(rows) == len(set(ids)), 'Duplicate forum identities')
        for order in orders.values():
            require(isinstance(order, list) and len(order) == len(rows) and set(order) == set(names),
                    'Every native order must cover every forum exactly once')
        by_name = {row['name']: row for row in rows}
        dates = [created(by_name[name]['created']) for name in orders['creation_date']]
        require(dates == sorted(dates, reverse=True), 'Native creation order differs from created DESC')
        minimum = min(created(row['created']) for row in rows)
        ties = {row['id'] for row in rows if created(row['created']) == minimum}
        require(created(native['minimum_created']) == minimum
                and isinstance(native['oldest_ids'], list)
                and all(type(value) is int for value in native['oldest_ids'])
                and len(native['oldest_ids']) == len(ties) and set(native['oldest_ids']) == ties,
                'Independent native SQL minimum/tie set disagrees with complete rows')
    else:
        require(native == WIKI_NATIVE, 'Actual native Wiki body/notice scope differs')
    return {'version': VERSION, 'source_task_id': sid, 'goal': source['goal'],
            'kind': kind, 'native': deepcopy(native)}


def local_document(page, site_origin):
    require(isinstance(page, dict) and isinstance(page.get('url'), str)
            and type(page.get('http_status')) is int
            and type(page.get('login_page')) is bool and type(page.get('error_page')) is bool,
            'Complete actual document status capture required')
    origin = urlsplit(site_origin)
    require(origin.scheme in ('http', 'https') and origin.hostname and origin.username is None
            and origin.password is None and origin.path in ('', '/') and not origin.query
            and not origin.fragment, 'Actual native site origin required')
    current = urlsplit(page['url'])
    valid = ((current.scheme, current.netloc) == (origin.scheme, origin.netloc)
             and current.username is None and current.password is None and not current.fragment
             and not current.query and 200 <= page['http_status'] < 300
             and not page['login_page'] and not page['error_page'])
    return bool(valid), current.path


def wiki_checks(capture, native):
    fields = capture.get('body_fields')
    require(isinstance(fields, list), 'Actual native body widget observation missing')
    matches = []
    for field in fields:
        require(isinstance(field, dict) and set(field) == {'id', 'name', 'tag', 'visible', 'labels', 'help_id', 'notices'}
                and all(isinstance(field[k], str) for k in ('id', 'name', 'tag'))
                and type(field['visible']) is bool and isinstance(field['labels'], list)
                and all(isinstance(x, str) for x in field['labels'])
                and (field['help_id'] is None or isinstance(field['help_id'], str))
                and isinstance(field['notices'], list), 'Incomplete body widget observation')
        notices = []
        for item in field['notices']:
            require(isinstance(item, dict) and set(item) == {'text', 'visible'}
                    and isinstance(item['text'], str) and type(item['visible']) is bool,
                    'Incomplete body-bound notice observation')
            if item['visible']:
                notices.append(' '.join(item['text'].split()))
        identity = (field['id'] == native['body_id'] and field['name'] == native['body_name']
                    and field['tag'] == 'TEXTAREA' and field['help_id'] == native['help_id'])
        if identity:
            matches.append(field['visible'] and field['labels'] == ['Body *']
                           and notices == [native['notice_text']])
    return len(matches) == 1 and matches[0]


def page_checks(reference, page, *, site_origin):
    valid, path = local_document(page, site_origin)
    capture = page.get('query2')
    require(isinstance(capture, dict) and capture.get('version') == VERSION
            and capture.get('source_task_id') == reference['source_task_id']
            and capture.get('kind') == reference['kind'], 'Missing/source-mismatched query observation')
    if reference['kind'] == 'oldest_forum':
        require(set(capture) == {'version', 'source_task_id', 'kind', 'forum_list'},
                'Complete forum directory observation required')
        checks = forum_list_checks({'sort': 'creation_date', 'reference': reference['native']['directory']},
                                  capture['forum_list'], page['url'])
        # Native reference completeness is a private integrity requirement.
        # The user need not inspect all 25 cards or all pages. Visible cards may
        # be a proper subset; require genuine labels and native relative order.
        state = capture['forum_list']
        match = re.fullmatch(r'/forums/by_creation_date(?:/([1-9][0-9]*))?', path)
        if not match or not valid or not checks['forum_sort_selected'] or not checks.get('forum_directory_controls'):
            return {'observed': False, 'forum_names': []}
        number = int(match[1] or 1)
        expected = reference['native']['directory']['orders']['creation_date'][(number - 1) * 25:number * 25]
        known = {row['name']: row for row in reference['native']['directory']['rows']}
        names = []
        for entry in state['entries']:
            require(isinstance(entry, dict) and isinstance(entry.get('path'), str)
                    and isinstance(entry.get('label'), str), 'Incomplete visible native card identity')
            name = unquote(entry['path']).removeprefix('/f/')
            if (entry['path'].startswith('/f/') and name in expected
                    and entry['label'] == '/f/' + name + ' ' + known[name]['title']):
                names.append(name)
            else:
                return {'observed': False, 'forum_names': []}
        ordered = len(names) == len(set(names)) and names == [name for name in expected if name in names]
        return {'observed': bool(names) and ordered, 'forum_names': names if ordered else []}
    require(set(capture) == {'version', 'source_task_id', 'kind', 'body_fields'},
            'Complete Wiki body observation required')
    widget = wiki_checks(capture, reference['native'])
    return {'observed': valid and path == '/wiki/_create' and widget, 'forum_names': []}


def answer_matches(reference, answer):
    if not isinstance(answer, dict):
        return False
    if reference['kind'] == 'wiki_markdown':
        return set(answer) == {'markdown_allowed'} and type(answer['markdown_allowed']) is bool and answer['markdown_allowed']
    if set(answer) != {'forum'} or not isinstance(answer['forum'], str):
        return False
    names = {row['name'] for row in reference['native']['directory']['rows']
             if row['id'] in reference['native']['oldest_ids']}
    return answer['forum'].strip() in names


def evaluate_history(binding, records, answer, *, site_origin, before_reference,
                     after_reference, before_protection, after_protection, trace_error=None):
    """Missing evidence stays unknown; complete wrong observations/answers fail.

    The caller must separately bind these private records to every actual Actor
    observation/request/archive. This function grants no Actor or metric access.
    """
    scope = {'eligible_for_training': False, 'evaluation_ready': False,
             'formal_test_metric': False, 'ordinary_actor_entry_qualified': False}
    def result(status, reason, **extra):
        return dict(scope, status=status, reward=None if status == 'unknown' else float(status == 'success'),
                    reason=reason, **extra)
    if trace_error:
        return result('unknown', 'runtime_or_evidence_error')
    try:
        source = binding['source']; sid, _ = validate_source(source)
        require(before_reference == after_reference == make_reference(source, before_reference['native']),
                'Native reference changed or is incomplete')
        baseline = validate_complete_snapshot(binding['protected_baseline'])
        require(validate_complete_snapshot(before_protection) == baseline
                and validate_complete_snapshot(after_protection) == baseline,
                'Complete native thirteen-table protection differs')
        require(isinstance(records, list) and records, 'Actual observed history missing')
        seen = []
        for index, row in enumerate(records):
            require(isinstance(row, dict) and set(row) == {'source_task_id', 'step', 'page'}
                    and row['source_task_id'] == sid and type(row['step']) is int and row['step'] == index,
                    'Complete consecutive source-bound observations required')
            seen.append(page_checks(before_reference, row['page'], site_origin=site_origin))
        correct = answer_matches(before_reference, answer)
        observed = any(item['observed'] for item in seen)
        named_object_seen = True
        if before_reference['kind'] == 'oldest_forum':
            name = answer.get('forum', '').strip() if isinstance(answer, dict) and isinstance(answer.get('forum'), str) else ''
            named_object_seen = any(item['observed'] and name in item['forum_names'] for item in seen)
        ok = observed and named_object_seen and correct
        return result('success' if ok else 'failure', 'query_completion_checked',
                      checks={'native_query_observed': observed, 'answered_object_observed': named_object_seen,
                              'answer_correct': correct},
                      observed_steps=[index for index, item in enumerate(seen) if item['observed']])
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        # Do not expose private references, minimum IDs, fields or routes.
        return result('unknown', 'incomplete_or_changed_native_evidence')
