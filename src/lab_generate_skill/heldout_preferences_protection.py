"""Original full13 plus an exact one-user/one-column comparison projection.

No table, other user, or other column is excused. last_seen remains the existing
published exception. All database reads require a quiescent owned instance.
"""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import re
from .heldout_preferences_binding import require, validate_binding, require_preferences_state

VERSION = 'heldout-preferences-exact-user-protection-v2'
CHUNKS_SHA256 = 'e3100ab46a6cc7fb0775af9b975a270cc639b9e87a91ddb3315bb10f71ed5ef3'
ORIGINAL = '''$projection=$table==='users' ? "(to_jsonb(r)-'last_seen')::text" : 'row_to_json(r)::text';'''


def isolated_scanner(user_id, field):
    """Reuse the proven bounded scanner without mutating its imported globals."""
    from . import reddit_protected_chunks as original
    require(type(user_id) is int and user_id > 0 and field in {'auto_fetch_submission_titles', 'timezone'},
            'Exact native target id/field required')
    path = Path(original.__file__)
    require(hashlib.sha256(path.read_bytes()).hexdigest() == CHUNKS_SHA256,
            'Reviewed bounded scanner bytes changed')
    spec = importlib.util.spec_from_file_location('lab_generate_skill._heldout_preferences_chunks', path)
    isolated = importlib.util.module_from_spec(spec); spec.loader.exec_module(isolated)
    require(isolated.PHP.count(ORIGINAL) == 1, 'Exact single reviewed users projection required')
    projection = ("CASE WHEN r.id = " + str(user_id) + " THEN (to_jsonb(r)-'last_seen'-'" + field
                  + "')::text ELSE (to_jsonb(r)-'last_seen')::text END")
    replacement = "$projection=$table==='users' ? \"" + projection + "\" : 'row_to_json(r)::text';"
    isolated.PHP = isolated.PHP.replace(ORIGINAL, replacement)
    require(original.PHP.count(ORIGINAL) == 1, 'Original scanner mutated')
    return isolated


def capture_guard(site, output, binding, *, browser_contexts_closed=False):
    from .heldout_parallel_protection import complete_snapshot
    from .site_preferences_rules import preference_state
    from .site_database import select_rows
    from .heldout_preferences_users_schema import capture_users_schema
    c = validate_binding(binding, executable=True)
    require(browser_contexts_closed is True and site.domain == 'reddit', 'Quiescent native Reddit instance required')
    output = Path(output)
    field = next(iter(c['preferences']['targets']))
    columns, catalog = capture_users_schema(site, output, field)
    full = complete_snapshot(site, output / 'full13-submissions.jsonl', browser_contexts_closed=True)
    prefs = require_preferences_state(c, preference_state(site, c['preferences']['username']))
    scanner = isolated_scanner(prefs['user_id'], field)
    keys = scanner.primary_keys(site, ['users'])
    require(keys == {'users': [{'name': 'id', 'type': 'bigint'}]}
            or keys == {'users': [{'name': 'id', 'type': 'integer'}]}, 'Original unique native users id required')
    masked = scanner.run_chunk_stream(site, keys, timeout=150)['users']
    require(masked['count'] == full['twelve_task_tables']['users']['count'], 'Complete users counts differ')
    return dict(version=VERSION, binding_sha256=binding['binding_sha256'],
                original_full13=full, preferences=prefs, users_columns=columns, users_catalog=catalog,
                projection=dict(user_id=prefs['user_id'], username=prefs['username'], field=field,
                                original_ignored_column='last_seen', digest=masked,
                                scanner_source_sha256=CHUNKS_SHA256,
                                actual_php_sha256=hashlib.sha256(scanner.PHP.encode()).hexdigest()))


def verify_transition(binding, before, after):
    from .reddit_native_read_runtime import validate_complete_snapshot
    from .heldout_preferences_users_schema import validate_users_schema
    c = validate_binding(binding, executable=True)
    field = next(iter(c['preferences']['targets']))
    for snapshot in (before, after):
        require(snapshot.get('version') == VERSION and snapshot.get('binding_sha256') == binding['binding_sha256'],
                'Source-bound protection snapshot required')
        state = require_preferences_state(c, snapshot['preferences'])
        full = validate_complete_snapshot(snapshot['original_full13'])
        projection = snapshot['projection']
        scanner = isolated_scanner(state['user_id'], field)
        require(set(projection) == {'user_id', 'username', 'field', 'original_ignored_column', 'digest',
                                     'scanner_source_sha256', 'actual_php_sha256'}
                and projection['user_id'] == state['user_id'] and projection['username'] == state['username']
                and projection['field'] == field and projection['original_ignored_column'] == 'last_seen'
                and projection['scanner_source_sha256'] == CHUNKS_SHA256
                and projection['actual_php_sha256'] == hashlib.sha256(scanner.PHP.encode()).hexdigest(),
                'Native single-user projection differs')
        d = projection['digest']
        require(set(d) == {'count', 'digest'} and type(d['count']) is int
                and d['count'] == full['twelve_task_tables']['users']['count'] and d['count'] > 0
                and isinstance(d['digest'], str) and re.fullmatch('[0-9a-f]{32}', d['digest']),
                'Whole projected users coverage required')
        validate_users_schema(snapshot['users_columns'], snapshot['users_catalog'], field)
    require(before['preferences']['user_id'] == after['preferences']['user_id']
            and before['users_columns'] == after['users_columns']
            and before['users_catalog'] == after['users_catalog'], 'Native account/schema changed')
    left, right = deepcopy(before['original_full13']), deepcopy(after['original_full13'])
    del left['twelve_task_tables']['users']; del right['twelve_task_tables']['users']
    require(left == right, 'Unrelated full13 protected records changed')
    require(before['projection'] == after['projection'], 'Another user or unallowed users field changed')
    return dict(other_twelve_tables_unchanged=True, complete_user_projection_equal=True,
                allowed_user_id=before['preferences']['user_id'], allowed_field=field,
                original_last_seen_exception_preserved=True)
