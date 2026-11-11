"""Compose the declared calendar account fixture before immutable cache state.

Reuse records are fresh read-only checks, never fabricated Rails invocations.
The account initializer and complete cache transition evidence remain required.
"""
from copy import deepcopy
import importlib
import json
from pathlib import Path

from .io_utils import atomic_write_json
from .gitlab_native_read_runtime import full_snapshot
from .gitlab_native_csv_probe import protected_snapshot_session
from .gitlab_persisted_goal_runtime import refs_snapshot, validate_refs
from .gitlab_prepared_cache_proof import verify_origin, reuse_sequence

VERSION = 'native-calendar-composed-baseline-reuse-v1'
PROFILE = 'calendar_wiki_issue'


def fixture():
    return importlib.import_module('gitlab_calendar_account_fixture')


def prepare_account(site):
    if site.generation != 0 or getattr(site, 'calendar_account_baseline', None) is not None:
        raise ValueError('Calendar fixture requires a fresh private baseline')
    from .site_auth import credentials
    username = credentials(site.root, 'gitlab')['username']
    directory = site.logs/'baseline-initialization/calendar-account'
    receipt = fixture().initialize(site, username, directory)
    fixture().verify(directory, receipt)
    site.calendar_account_baseline = dict(username=username, receipt=receipt)


def _original_composition(site, username):
    if getattr(site, 'initialization_profile', None) != PROFILE:
        raise ValueError('Prepared calendar composition required')
    account = getattr(site, 'calendar_account_baseline', None)
    cache = getattr(site, 'prepared_initialization', None)
    if not account or account['username'] != username or not cache or cache['profile'] != PROFILE:
        raise ValueError('Current account and composed cache baseline required')
    original = fixture().verify(site.logs/'baseline-initialization/calendar-account', account['receipt'])
    phases = verify_origin(cache['original_evidence'])
    if original['full_after'] != phases[0]['cold'] or cache['prepared_after'] != phases[-1]['after']:
        raise ValueError('Account initialization must precede the complete cache transition')
    return original, cache, phases


def _save_reuse(site, username, directory, original, cache, phases, actual, refs):
    full_snapshot(actual); validate_refs(refs)
    if actual != phases[-1]['after'] or refs != original['refs_after']:
        raise ValueError('Restored calendar account/cache state or repository state differs')
    from . import evidence_store
    root = Path(getattr(site, 'native_cache_evidence_root', directory.parent))
    row = dict(version=VERSION, initializer_invoked=False, username=username,
               original_account=deepcopy(original), original_cache=cache['original_evidence'],
               full_after=actual, refs_after=refs)
    evidence_store.write(directory/'composed-account.json', row, root=root)
    return dict(version=VERSION, initializer_invoked=False, username=username,
                full_after=actual, refs_after=refs)


def initialize(site, username, directory):
    if getattr(site, 'initialization_profile', None) != PROFILE:
        return fixture().initialize(site, username, directory)
    original, cache, phases = _original_composition(site, username)
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
    actual = protected_snapshot_session(site, directory/'fresh-full16.jsonl')
    refs = refs_snapshot(site)
    return _save_reuse(site, username, directory, original, cache, phases, actual, refs)


def prepare_reused(site, username, directory, cache_directory):
    """Validate account and cache from one fresh full-state capture.

    This operation owns the fresh cache query and repository capture. No state
    from an earlier control, another instance or an actor is accepted as input.
    Both original proof formats and all their comparisons remain unchanged.
    """
    original, cache, phases = _original_composition(site, username)
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
    cold, actual, effects = reuse_sequence(site, cache_directory)
    refs = refs_snapshot(site)
    account = _save_reuse(site, username, directory, original, cache, phases, actual, refs)
    return account, cold, actual, effects, refs


def verify(directory, expected):
    if expected.get('version') != VERSION:
        return fixture().verify(directory, expected)
    from . import evidence_store
    row = evidence_store.read(Path(directory)/'composed-account.json')
    if (row.get('version') != VERSION or row.get('initializer_invoked') is not False
            or expected != {k: row[k] for k in ('version','initializer_invoked','username','full_after','refs_after')}):
        raise ValueError('Original fresh calendar reuse receipt differs')
    original = row['original_account']
    # Verify the full native invocation using its original verifier in a private
    # temporary proof folder; this neither mutates nor fabricates website state.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='calendar-origin-proof-') as tmp:
        atomic_write_json(Path(tmp)/'actual-native-fixture.json', original)
        fixture().verify(tmp, original)
    phases = verify_origin(row['original_cache'])
    full_snapshot(row['full_after']); validate_refs(row['refs_after'])
    if (original['full_after'] != phases[0]['cold'] or row['full_after'] != phases[-1]['after']
            or row['refs_after'] != original['refs_after']):
        raise ValueError('Original account/cache/current state chain differs')
    return expected
