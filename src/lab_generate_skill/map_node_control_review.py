"""Recompute editor control evidence; never turn a report flag into admission.

Input members must already be authenticated against the archive index. This
review does not run a browser or call a model and cannot publish training data.
"""
import json
from urllib.parse import urlsplit
from .map_node_task import evaluate_set, environment_key
from .map_node_readout import validate_snapshot
from .map_candidate_start import validate_initial
from .map_reset_guard import checked_state
from .frozen_node_actor_adapter import initial_signature

CONTROLS = {'noop': 'failure', 'wrong_object': 'failure',
            'unsaved': 'failure', 'positive': 'success'}
EVENTS = ['prepare', 'attach', 'initialize_browser', 'observe_initial',
          'capture_terminal', 'close', 'score_terminal']


def checkpoint(candidate, initial, record, label, expected):
    actual = evaluate_set(candidate, initial, record['audit'], record['snapshot'])
    if (record.get('label') != label or record.get('expected') != expected
            or record.get('passed') is not True or record.get('judgment') != actual
            or actual['status'] != expected):
        raise ValueError('Native control readback does not support ' + label)
    return actual


def verify_initialization(candidate, profile, initial):
    if initial['environment'] != environment_key(candidate, profile):
        raise ValueError('Reviewed native initializer differs from public task')
    validate_snapshot(initial['snapshot'])
    fixtures = candidate['initialization']['fixtures']
    if set(initial['fixture_ids']) != {f['key'] for f in fixtures}:
        raise ValueError('Declared fixture keys differ')
    records = {r['node_id']: r['record'] for r in initial['snapshot']['records']}
    ids = list(initial['fixture_ids'].values())
    if len(set(ids)) != len(ids) or set(records) != set(ids):
        raise ValueError('Declared fixture identity is incomplete')
    for f in fixtures:
        rec = records[initial['fixture_ids'][f['key']]]
        n = rec['current']
        if (n is None or n['version'] != 1 or n['visible'] is not True
                or rec['changeset_owner'] != initial['owner_id']
                or {t['k']: t['v'] for t in rec['tags']} != f['tags']
                or n['latitude'] != round(float(f['latitude']) * 1e7)
                or n['longitude'] != round(float(f['longitude']) * 1e7)):
            raise ValueError('Saved fixture differs from declared initial state')
    return True


def review_source(candidate, profile, raw, *, prefix=None, reset_only=False):
    sid = candidate['source_task_id']
    prefix = (prefix or sid).rstrip('/') + '/'
    def read(name):
        return json.loads(raw[prefix + name + '.json'])
    initial = read('node-initialization')
    verify_initialization(candidate, profile, initial)
    page = read('node-initial-page')
    u = urlsplit(page['url'])
    expected = urlsplit(candidate['start_path'])
    if (u.path, u.query, u.fragment) != (expected.path, expected.query, expected.fragment):
        raise ValueError('Reviewed episode did not begin at the declared source')
    if expected.path == '/':
        validate_initial(candidate, u.scheme + '://' + u.netloc, page['url'],
                         page['view'], page.get('route'))
    observation = read('initial-observation')
    if observation.get('goal') != candidate['goal']:
        raise ValueError('Recorded public task differs from declared goal')
    if not observation.get('axtree_txt', '').strip():
        raise ValueError('Original actor observation is missing')
    required = {'noop': 'failure'} if reset_only else CONTROLS
    for label, status in required.items():
        checkpoint(candidate, initial, read(label + '-checkpoint'), label, status)
    terminal = read('node-terminal')
    checked_state(terminal['guard'])
    if (terminal.get('events') != EVENTS or terminal.get('integrity') is not True
            or terminal.get('dirty_state_not_cleared') is not True
            or terminal['terminal'] != read('terminal-page')):
        raise ValueError('Ordinary terminal lifecycle or retained dirty state differs')
    actual = evaluate_set(candidate, initial, terminal['audit'], terminal['final'])
    if (actual != terminal['judgment']
            or actual['status'] != ('failure' if reset_only else 'success')):
        raise ValueError('Saved terminal state does not support reported result')
    return dict(source_task_id=sid, controls=dict(required),
                frozen_evaluator_recomputed=True, original_start_verified=True,
                clean_initialization_verified=True,
                reset_signature=initial_signature(initial), terminal=actual)
