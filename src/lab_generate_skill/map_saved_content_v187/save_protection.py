"""Bound native save effects while protecting all unrelated persistent state.

The guard permits native fields and rows belonging to newly saved records. It
does not require the requested title, body, visibility, or GPX contents; those
are business checks. Original records and unrelated tables remain protected.
"""
from collections import Counter
import json
import re

VERSION = 'native-map-save-protection-v187'
COMMON = {'users', 'user_preferences'}
DIARY = {'diary_entries', 'diary_entry_subscriptions'}
UPLOAD = {'gpx_files', 'gpx_file_tags', 'gps_points', 'active_storage_blobs',
          'active_storage_attachments', 'active_storage_variant_records'}
ROW_TABLES = sorted(((COMMON | DIARY | UPLOAD) - {'users'}) | {'delayed_jobs'})
SEQUENCES = {
    'diary': {'diary_entries_id_seq'},
    'upload': {'gpx_files_id_seq', 'gpx_file_tags_id_seq', 'active_storage_blobs_id_seq',
               'active_storage_attachments_id_seq', 'active_storage_variant_records_id_seq'},
}


def rows(value):
    if not isinstance(value, dict) or set(value) != set(ROW_TABLES):
        raise ValueError('Complete bounded native side-effect inventory required')
    if any(not isinstance(v, list) or len(v) > 5000 or any(not isinstance(r, dict) for r in v) for v in value.values()):
        raise ValueError('Malformed or oversized native row inventory')
    return value


def added_rows(before, after):
    key = lambda row: json.dumps(row, sort_keys=True, separators=(',', ':'))
    first, last = Counter(map(key, before)), Counter(map(key, after))
    if first - last:
        raise ValueError('A protected existing row changed or disappeared')
    return [json.loads(raw) for raw, count in (last - first).items() for _ in range(count)]


def _keyed(values, field='id'):
    result = {r[field]: r for r in values}
    if len(result) != len(values):
        raise ValueError('Duplicate native record identity')
    return result


def check(kind, before, after, *, files_before, files_after):
    """Return guarded facts; absent or inconsistent evidence cannot be passed."""
    facts = {}
    try:
        if kind not in SEQUENCES:
            raise ValueError('Known save family required')
        a, b = before['guard'], after['guard']
        for state in (a, b):
            if not state['tables'] or state['tables'] != state['tracked']:
                raise ValueError('Every public table must have an enabled write trigger')
        if a['changed'] or a['tables'] != b['tables']:
            raise ValueError('Clean original table baseline required')
        allowed = COMMON | (DIARY if kind == 'diary' else UPLOAD)
        if not set(b['changed']) <= {'public.' + name for name in allowed}:
            raise ValueError('Unrelated native table changed')
        initial, final = dict(a['sequences']), dict(b['sequences'])
        if initial.keys() != final.keys() or any(initial[k] != final[k] for k in initial if k not in SEQUENCES[kind]):
            raise ValueError('Unrelated native sequence changed')
        facts['all_public_tables_and_sequences_protected'] = True
        old, new = rows(before['rows']), rows(after['rows'])
        additions = {}
        for table in ROW_TABLES:
            if table == 'user_preferences':
                continue
            additions[table] = added_rows(old[table], new[table])
            if table not in allowed and additions[table]:
                raise ValueError('Unrelated native records appeared')
        target = 'diary_entries' if kind == 'diary' else 'gpx_files'
        created = _keyed(additions[target])
        if any(type(i) is not int or i <= 0 for i in created):
            raise ValueError('New native record identity malformed')
        users_before, users_after = _keyed(before['users']), _keyed(after['users'])
        if users_before.keys() != users_after.keys():
            raise ValueError('Native user inventory changed')
        owners = {r['user_id'] for r in created.values()}
        if any(type(i) is not int or i <= 0 or i not in users_before for i in owners):
            raise ValueError('New native record owner is not an existing account')
        counts = Counter(r['user_id'] for r in created.values())
        changed_counter = 'diary_entries_count' if kind == 'diary' else 'traces_count'
        for ident, user in users_before.items():
            expected = dict(user)
            expected[changed_counter] += counts[ident]
            if users_after[ident] != expected:
                raise ValueError('Native user changed beyond its native save counter')
        facts['preexisting_rows_and_users_protected'] = True
        preference_key = 'diary.default_language' if kind == 'diary' else 'gps.trace.visibility'
        key = lambda r: (r['user_id'], r['k'])
        old_prefs, new_prefs = {key(r): r for r in old['user_preferences']}, {key(r): r for r in new['user_preferences']}
        if len(old_prefs) != len(old['user_preferences']) or len(new_prefs) != len(new['user_preferences']):
            raise ValueError('Ambiguous native preferences')
        for ident in old_prefs.keys() | new_prefs.keys():
            if old_prefs.get(ident) == new_prefs.get(ident):
                continue
            current = new_prefs.get(ident)
            values = {r['language_code' if kind == 'diary' else 'visibility'] for r in created.values() if r['user_id'] == ident[0]}
            if ident[0] not in owners or ident[1] != preference_key or not current or current['v'] not in values:
                raise ValueError('Unrelated native preference changed')
        facts['native_preference_effects_bound'] = True
        if kind == 'diary':
            for row in additions['diary_entry_subscriptions']:
                entry = created.get(row['diary_entry_id'])
                if not entry or row['user_id'] != entry['user_id']:
                    raise ValueError('Diary subscription is not the new entry owner')
            allowed_files = set()
        else:
            for table in ('gpx_file_tags', 'gps_points'):
                if any(row['gpx_id'] not in created for row in additions[table]):
                    raise ValueError('Native trace data belongs to a different record')
            blobs = _keyed(additions['active_storage_blobs'])
            attachments = additions['active_storage_attachments']
            for row in attachments:
                if row['record_type'] != 'Trace' or row['record_id'] not in created or row['blob_id'] not in blobs or row['name'] not in ('file', 'image', 'icon'):
                    raise ValueError('Unrelated native attachment appeared')
            if set(blobs) != {r['blob_id'] for r in attachments}:
                raise ValueError('Unbound native blob appeared')
            for row in additions['active_storage_variant_records']:
                if row['blob_id'] not in blobs:
                    raise ValueError('Unrelated native storage variant appeared')
            allowed_files = set()
            for blob in blobs.values():
                key = blob['key']
                if not re.fullmatch(r'[A-Za-z0-9_-]+', key) or len(key) < 5:
                    raise ValueError('Native blob storage key malformed')
                allowed_files.add('storage/' + key[:2] + '/' + key[2:4] + '/' + key)
        original_files, final_files = dict(files_before), dict(files_after)
        if len(original_files) != len(files_before) or len(final_files) != len(files_after):
            raise ValueError('Duplicate persistent file identity')
        if any(final_files.get(name) != digest for name, digest in original_files.items()):
            raise ValueError('Protected native file changed or disappeared')
        if set(final_files) - set(original_files) != allowed_files:
            raise ValueError('Unbound persistent native file appeared or upload file missing')
        facts['only_bound_native_save_effects'] = True
        facts['preexisting_and_unrelated_files_protected'] = True
        return dict(version=VERSION, passed=True, checks=facts, new_native_records=len(created))
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
        return dict(version=VERSION, passed=False, checks=facts, error=str(error))
