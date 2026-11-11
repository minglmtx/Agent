"""Explicit three-level native fixture for otherwise impossible hierarchy tasks.

This initializer is opt-in and has no actor or evaluator behavior. Admission
must separately validate the changed initial state and actual native controls.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time

from .gitlab_native_csv_probe import native_command
from .io_utils import atomic_write_json
from .site_state_snapshot import SiteStateSnapshot

VERSION = 'gitlab-local-hierarchy-fixture-v1'
INITIALIZER_VERSION = 'gitlab-native-hierarchy-fixed-clock-v2'
FIXTURE_CREATED_AT = '2023-01-01T00:00:00Z'
DECLARATION = {'version': VERSION, 'levels': [
    {'name': 'Local Training Groups', 'path': 'local-training-groups'},
    {'name': 'Engineering', 'path': 'engineering'},
    {'name': 'Platform', 'path': 'platform'}]}


def revise_contract(contract):
    """Declare the changed initial data in both model inputs and source mapping."""
    from .source_revision_binding import binding
    binding(contract)
    if contract.get('family') != 'native_group_hierarchy':
        raise ValueError('Only a native group hierarchy task may use this fixture')
    value = deepcopy(contract)
    goal = ('In the local training environment containing the Local Training Groups / '
            'Engineering / Platform hierarchy, expand one subgroup in the native '
            'group hierarchy and leave its nested subgroups visible.')
    value['goal'] = goal
    value['task_text_changed'] = goal != value['original_goal']
    value['goal_revision'] = dict(version=VERSION, original_goal=value['original_goal'],
        derived_goal=goal, reason='Declare the local nested-group baseline absent from the original seed.',
        equivalent_to_original_goal=False)
    value['initial_state_revision'] = dict(version=VERSION, declaration=deepcopy(DECLARATION),
        reason='Create native groups before recording a clean baseline; preserve all existing groups.',
        equivalent_to_original_initial_state=False)
    value['public_parameters']['initial_hierarchy'] = deepcopy(DECLARATION)
    value['public_task_input']['goal'] = goal
    value['public_task_input']['public_parameters'] = deepcopy(value['public_parameters'])
    binding(value)
    return value


def declaration_for(contract):
    """Initialization must be explicitly declared, never inferred from task ID."""
    if contract.get('family') != 'native_group_hierarchy':
        return None
    revision = contract.get('initial_state_revision', {})
    declaration = validate_declaration(contract.get('public_parameters', {}).get('initial_hierarchy'))
    if (revision.get('version') != VERSION or revision.get('declaration') != declaration
            or revision.get('equivalent_to_original_initial_state') is not False
            or contract.get('public_task_input', {}).get('public_parameters') != contract['public_parameters']):
        raise ValueError('Public and private initial hierarchy declarations must agree')
    return declaration


def prepare_batch(site, cases, username, directory):
    """One declared environment profile per worker, before its first reset.

    Ordinary actor and CPU-control entries use the same initialization. Mixing
    seed-only tasks with this fixture would change their starting state.
    """
    if not cases:
        raise ValueError('At least one task is required')
    declarations = [declaration_for(c) for c in cases]
    first = declarations[0]
    if any(d != first for d in declarations):
        raise ValueError('Different initial-state profiles require isolated workers')
    if first is None:
        return None
    previous = getattr(site, 'prepared_hierarchy', None)
    if previous is not None:
        if previous.get('declaration') != first or previous.get('username') != username:
            raise ValueError('Prepared hierarchy belongs to another initial state or account')
        require_initializer_version(previous)
        return previous
    return prepare(site, username, first, directory)


def require_prepared(site, contract, username):
    declaration = declaration_for(contract)
    receipt = getattr(site, 'prepared_hierarchy', None)
    if (not isinstance(receipt, dict) or receipt.get('declaration') != declaration
            or receipt.get('username') != username or receipt.get('existing_groups_unchanged') is not True):
        raise ValueError('Declared hierarchy must be initialized before task reset or inference')
    require_initializer_version(receipt)
    return receipt


def require_initializer_version(receipt):
    if (receipt.get('initializer_version') != INITIALIZER_VERSION
            or receipt.get('fixture_created_at') != FIXTURE_CREATED_AT):
        raise ValueError('Deterministic hierarchy initializer receipt required; old baseline cannot be reused')


def validate_declaration(value):
    if not isinstance(value, dict) or set(value) != {'version', 'levels'} or value['version'] != VERSION:
        raise ValueError('Versioned explicit hierarchy fixture required')
    if not isinstance(value['levels'], list) or len(value['levels']) != 3:
        raise ValueError('Root, subgroup and nested subgroup required')
    for level in value['levels']:
        if (not isinstance(level, dict) or set(level) != {'name', 'path'}
                or not isinstance(level['name'], str) or not 1 <= len(level['name']) <= 100
                or not level['name'].strip() or any(ord(c) < 32 for c in level['name'])
                or not isinstance(level['path'], str)
                or not re.fullmatch('[a-z][a-z0-9-]{1,47}', level['path'])):
            raise ValueError('Explicit valid native group names and paths required')
    return deepcopy(value)


def prepare(site, username, declaration, directory):
    """Create real groups on a fresh site, then freeze their unexpanded baseline."""
    declaration = validate_declaration(declaration)
    if (getattr(site, 'domain', None) != 'gitlab' or not getattr(site, 'reuse_state', False)
            or getattr(site, 'generation', None) != 0 or getattr(site, 'stopped', True)
            or getattr(site, 'prepared_initialization', None) is not None
            or getattr(site, 'prepared_hierarchy', None) is not None):
        raise ValueError('Hierarchy fixture requires a fresh reusable native site before any rollout')
    if not isinstance(username, str) or not username or len(username) > 255:
        raise ValueError('Explicit native actor account required')
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='hierarchy-fixture-', dir=site.state) as folder:
        folder = Path(folder)
        request = dict(declaration, username=username)
        request_path = folder / 'request.json'
        atomic_write_json(request_path, request); request_path.chmod(0o600)
        ruby = Path(__file__).with_suffix('.rb')
        (folder / 'initialize.rb').write_bytes(ruby.read_bytes())
        (folder / 'initialize.rb').chmod(0o600)
        relative = '/state/' + folder.name
        native_command(site, ['bash', '/state/service.sh', 'gitlab-rails', 'env',
            'RAILS_ENV=production', 'LAB_HIERARCHY_FIXTURE_REQUEST=' + relative + '/request.json',
            '/opt/gitlab/embedded/bin/bundle', 'exec',
            '/opt/gitlab/embedded/service/gitlab-rails/bin/rails', 'runner', '-e', 'production',
            relative + '/initialize.rb'], seconds=300)
        receipt = json.loads((folder / 'receipt.json').read_text())
    require_initializer_version(receipt)
    if (receipt.get('version') != VERSION or receipt.get('username') != username
            or receipt.get('existing_groups_unchanged') is not True
            or len(receipt.get('created_groups', [])) != 3):
        raise ValueError('Actual native hierarchy initialization receipt required')
    receipt.update(declaration=declaration, initializer_sha256=hashlib.sha256(ruby.read_bytes()).hexdigest(),
                   task_initial_state_changed=True, original_benchmark_equivalence=False,
                   native_controls_verified=False, training_admitted=False)
    atomic_write_json(directory / 'initialization.json', receipt)
    # Snapshot only when every service writer has stopped. The fixture is part
    # of the initial environment; subsequent resets must retain the same IDs.
    site.stop_services(); site.snapshot.close()
    replacement_temp = tempfile.TemporaryDirectory(prefix='gitlab-hierarchy-baseline-', dir=site.state.parent)
    try:
        replacement = SiteStateSnapshot(site.state, Path(replacement_temp.name) / 'state',
            services_stopped=lambda: site.stopped, restore_strategy=site.reset_strategy)
        replacement.save()
    except BaseException:
        replacement_temp.cleanup()
        raise
    previous_temp = site.baseline_temp
    site.snapshot = replacement; site.baseline_temp = replacement_temp
    previous_temp.cleanup()
    site.prepared_hierarchy = receipt
    site.prepare_next_reset(); site.start_services()
    site.timed('prepare_hierarchy_baseline', started, profile=VERSION)
    return receipt
