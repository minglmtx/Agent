"""Terminal-only exact native forum creation for explicit task revisions.

The original two-fresh CPU proof is required unchanged. Native fields, tag
UUIDs, protected rows and expected values remain private. The actor receives
only the declared public task, current AX and the ordinary six-step history.
"""
import copy
import json
import re
import hashlib
from datetime import datetime
from uuid import UUID
from pathlib import Path
from urllib.parse import urlsplit

from . import reddit_exact_forum as forum
from . import reddit_remaining_exact as normal
from .io_utils import atomic_write_json
from .reddit_protected_chunks import full_digest, validate_snapshot
from .site_database import select_rows

VERSION = 'reddit-exact-forum-native-runtime-v2'
ALLOWED_CHANGED_TABLES = {'forums', 'forum_tags', 'forums_tags'}
TABLES = ('forums', 'comments', 'submission_votes', 'comment_votes', 'wiki_pages',
          'wiki_revisions', 'forum_tags', 'forums_tags', 'hidden_forums',
          'forum_subscriptions', 'user_blocks', 'users')
HEAVY_TABLES = ('comments', 'comment_votes', 'submission_votes', 'users')


def enabled(contract):
    if 'exact_forum_creation' not in contract:
        return False
    forum.validate_contract(contract)
    if any(contract.get(key) for key in ('reddit_native_task', 'query', 'membership',
           'preferences', 'forum_creation', 'submission', 'wiki', 'search', 'cart',
           'vote', 'fork_creation', 'project_creation', 'group_creation', 'issue_creation',
           'ref_creation', 'account_change', 'checkout', 'order', 'map_export')):
        raise ValueError('Exact forum creation cannot mix another task family')
    return True


def require_admission(contract, proof):
    if not enabled(contract):
        raise ValueError('Exact native forum task required')
    # This is the existing strict normal gate, including native wrong-field/tag
    # controls, both fresh sites, all-user protection and complete restoration.
    normal.require_admission(contract, proof)


def bind_normal_contract(original, *, admission_path):
    if not enabled(original) or original.get('eligible_for_training') is not False:
        raise ValueError('Reviewed development exact forum derivative required')
    if any(key in original for key in ('completion', 'runtime_version', 'shared_runtime_ready', 'admission_result')):
        raise ValueError('Original CPU binding must not already be a runtime binding')
    value = copy.deepcopy(original)
    value.update(completion={}, runtime_version=VERSION, shared_runtime_ready=False,
                 admission_result=str(admission_path))
    return value


def _path(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Original native start URL required')
    parsed = urlsplit(value)
    return (parsed.path or '/') + ('?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')


def require_original_binding(contract, original, inventory):
    """Only a declared compatibility transformation of the authoritative source.

    Alias, reservation, exact terminal Slurm job and attempt checks remain in
    the shared first-actor gate; this function never suppresses those checks.
    """
    expected = bind_normal_contract(original, admission_path=contract.get('admission_result', ''))
    if json.dumps(expected, sort_keys=True) != json.dumps(contract, sort_keys=True):
        raise ValueError('Runtime changed the original exact forum declaration')
    if (not isinstance(inventory, dict) or inventory.get('domain') != 'reddit'
            or inventory.get('task_id') != contract.get('source_task_id')
            or inventory.get('heldout_quarantine') is not False
            or inventory.get('goal') != contract.get('original_goal')
            or inventory.get('source_trace_ids') != contract.get('source_trace_ids')
            or [_path(url) for url in inventory.get('recorded_start_urls', [])] != contract.get('recorded_start_paths')
            or not contract.get('recorded_start_paths')
            or contract.get('start_path') != contract['recorded_start_paths'][0]):
        raise ValueError('Authoritative original goal/start/trace mapping changed')


def _small_digest_query(tables):
    if not tables or len(set(tables)) != len(tables) or not set(tables) <= set(TABLES) - set(HEAVY_TABLES):
        raise ValueError('Whitelisted native small protected tables required')
    parts = []
    for table in tables:
        limbs = ["COALESCE(sum(('x'||substr(h," + str(i) + ",8))::bit(32)::bigint)::text,'0')" for i in (1, 9, 17, 25)]
        parts.append("SELECT '" + table + "' AS table_name,count(*) AS count,md5(" + "||':'||".join(limbs) + ") AS digest FROM (SELECT md5(row_to_json(r)::text) AS h FROM " + table + " r OFFSET 0) full_rows")
    return ' UNION ALL '.join(parts) + ' ORDER BY table_name'


def protected_snapshot(site):
    """Read the same complete, bounded native snapshot used by CPU controls."""
    small = tuple(table for table in TABLES if table not in HEAVY_TABLES)
    rows = select_rows(site, _small_digest_query(small))
    if (not isinstance(rows, list) or len(rows) != len(small)
            or {row.get('table_name') for row in rows} != set(small)
            or any(type(row.get('count')) is not int or row['count'] < 0
                   or not isinstance(row.get('digest'), str)
                   or not re.fullmatch('[0-9a-f]{32}', row['digest']) for row in rows)):
        raise ValueError('Complete native small protected table result required')
    value = {row['table_name']: {'count': row['count'], 'digest': row['digest']} for row in rows}
    value.update(full_digest(site, list(HEAVY_TABLES)))
    validate_snapshot(value)
    return value


SUBSCRIPTION_FIELDS = {'id', 'user_id', 'forum_id', 'subscribed_at'}


def _subscription_digest(records):
    # Exactly the existing native small-table aggregate over PostgreSQL's own
    # full row_to_json bytes. Python never recreates a native row hash.
    limbs = [sum(int(record['row_hash'][i:i+8], 16) for record in records)
             for i in (0, 8, 16, 24)]
    return {'count': len(records), 'digest': hashlib.md5(
        ':'.join(map(str, limbs)).encode()).hexdigest()}


def validate_subscription_snapshot(snapshot):
    if not isinstance(snapshot, dict) or set(snapshot) != {'columns', 'records', 'native_digest'}:
        raise ValueError('Complete native subscription row/schema snapshot required')
    columns = snapshot['columns']
    if (not isinstance(columns, list) or len(columns) != len(SUBSCRIPTION_FIELDS)
            or set(columns) != SUBSCRIPTION_FIELDS or len(set(columns)) != len(columns)):
        raise ValueError('Every installed native subscription column required')
    records = snapshot['records']
    if not isinstance(records, list):
        raise ValueError('Complete native subscription record list required')
    keys, ids = [], []
    for record in records:
        if not isinstance(record, dict) or set(record) != {'row', 'row_hash'}:
            raise ValueError('Complete native subscription row and PostgreSQL hash required')
        row = record['row']
        if (not isinstance(row, dict) or set(row) != set(columns)
                or type(row['user_id']) is not int or row['user_id'] <= 0
                or type(row['forum_id']) is not int or row['forum_id'] <= 0
                or not isinstance(row['id'], str) or str(UUID(row['id'])) != row['id']
                or not isinstance(row['subscribed_at'], str)
                or not isinstance(record['row_hash'], str)
                or not re.fullmatch('[0-9a-f]{32}', record['row_hash'])):
            raise ValueError('Malformed native full subscription row')
        stamp = datetime.fromisoformat(row['subscribed_at'])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError('Native subscription timestamp timezone required')
        keys.append((row['user_id'], row['forum_id'])); ids.append(row['id'])
    if len(set(keys)) != len(keys) or len(set(ids)) != len(ids):
        raise ValueError('Duplicate native account/forum or subscription UUID')
    digest = snapshot['native_digest']
    if (not isinstance(digest, dict) or set(digest) != {'count', 'digest'}
            or type(digest['count']) is not int or digest['count'] < 0
            or not isinstance(digest['digest'], str)
            or not re.fullmatch('[0-9a-f]{32}', digest['digest'])):
        raise ValueError('Exact native subscription aggregate types required')
    if digest != _subscription_digest(records):
        raise ValueError('Complete row hashes do not match native protected digest')


def subscription_snapshot(site, native_digest):
    columns = select_rows(site, "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='forum_subscriptions' ORDER BY ordinal_position")
    records = select_rows(site, "SELECT row_to_json(s) AS row,md5(row_to_json(s)::text) AS row_hash "
        "FROM forum_subscriptions s ORDER BY user_id,forum_id,id")
    value = {'columns': [row['column_name'] for row in columns],
             'records': records, 'native_digest': native_digest}
    validate_subscription_snapshot(value)
    return value


def creator_subscriptions_unchanged(before, after, *, user_id, initial_forums, final_forums):
    """Protect all old rows; allow zero or one native creator/new-forum row.

    This protects a native creation side effect and adds no subscription goal.
    Unsubscribing the newly created forum is permitted; old subscriptions are
    still immutable, including their UUID/timestamp and PostgreSQL row hash.
    """
    validate_subscription_snapshot(before); validate_subscription_snapshot(after)
    if before['columns'] != after['columns']:
        return False
    if type(user_id) is not int or user_id <= 0:
        raise ValueError('Exact native creator account required')
    old = {record['row']['id']: record for record in before['records']}
    current = {record['row']['id']: record for record in after['records']}
    if any(current.get(key) != record for key, record in old.items()):
        return False
    extras = [record for key, record in current.items() if key not in old]
    if not extras:
        return True
    old_ids = {row['id'] for row in initial_forums}
    added = [row for row in final_forums if row['id'] not in old_ids]
    return (len(extras) == 1 and len(added) == 1
            and extras[0]['row']['user_id'] == user_id
            and extras[0]['row']['forum_id'] == added[0]['id'])


def unrelated_unchanged(before, after, *, verified_creator_subscription=False):
    validate_snapshot(before)
    validate_snapshot(after)
    # The exact evaluator separately checks every original forum row/relation,
    # original tag/link and the allowed new forum/tag ownership. Only those
    # forum/tag table digests can legitimately change. The complete subscription
    # table is protected separately row by row, allowing only creator/new-forum.
    allowed = ALLOWED_CHANGED_TABLES | ({'forum_subscriptions'} if verified_creator_subscription is True else set())
    return all(before[table] == after[table] for table in TABLES if table not in allowed)


class ExactForumHooks:
    def __init__(self, contract, proof, directory):
        require_admission(contract, proof)
        self.contract, self.proof, self.directory = contract, proof, Path(directory)
        self.before = None
        self.protected_before = None
        self.subscriptions_before = None

    def verify_baseline(self, site, username):
        value = forum.state(site, username)
        forum.validate_initial(self.contract, value)
        protected = protected_snapshot(site)
        # Save real diagnostics before rejecting a changed native reset.
        subscriptions = subscription_snapshot(site, protected['forum_subscriptions'])
        atomic_write_json(self.directory / 'exact-forum-private-before.json',
                          {'state': value, 'protected': protected, 'subscriptions': subscriptions})
        if (value != self.proof['cycles'][0]['initial_state']
                or protected != self.proof['cycles'][0]['private_protected_before']):
            raise ValueError('Exact forum native reset differs from admitted controls')
        self.before, self.protected_before = value, protected
        self.subscriptions_before = subscriptions
        return value

    def score_terminal(self, site, username, page, *, runtime_error=None):
        if self.before is None:
            raise ValueError('Verified native initial state required before inference')
        after = forum.state(site, username, self.before)
        protected = protected_snapshot(site)
        subscriptions = subscription_snapshot(site, protected['forum_subscriptions'])
        atomic_write_json(self.directory / 'exact-forum-private-after.json',
                          {'state': after, 'protected': protected, 'subscriptions': subscriptions})
        judgment = forum.evaluate(self.contract, page, self.before, after, site_origin=site.url, runtime_error=runtime_error)
        subscription_integrity = creator_subscriptions_unchanged(
            self.subscriptions_before, subscriptions, user_id=self.before['submissions']['user_id'],
            initial_forums=self.before['forums'], final_forums=after['forums'])
        integrity = unrelated_unchanged(self.protected_before, protected,
            verified_creator_subscription=subscription_integrity) and subscription_integrity
        return judgment, integrity


def feedback(judgment):
    """Predicate outcomes only: no private state, IDs, field values or actions."""
    return {'status': judgment.get('status'), 'reward': judgment.get('reward'),
            'checks': {key: value for key, value in judgment.get('checks', {}).items() if type(value) is bool},
            'scope': 'Declared native persistence and unrelated-state integrity after termination.'}
