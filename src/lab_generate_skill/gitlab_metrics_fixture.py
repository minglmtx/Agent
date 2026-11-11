"""Explicit local Metrics visibility baseline, never an actor-side repair.

The public project already exists. This opt-in fixture changes only its Metrics
feature visibility, without adding metric data, users, memberships or services.
Native admission must still verify the real page and its negative controls.
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

VERSION = 'gitlab-local-metrics-visibility-v1'
FIXTURE_TIME = '2023-01-01T00:00:00Z'


def validate_declaration(value):
    if (not isinstance(value, dict)
            or set(value) != {'version', 'project', 'from_level', 'to_level'}
            or value.get('version') != VERSION
            or type(value.get('from_level')) is not int or value['from_level'] != 10
            or type(value.get('to_level')) is not int or value['to_level'] != 20
            or not isinstance(value.get('project'), str)
            or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]*)+', value['project'])
            or any(x in ('.', '..') for x in value['project'].split('/'))):
        raise ValueError('Explicit target-project PRIVATE-to-ENABLED Metrics fixture required')
    return deepcopy(value)


def revise_contract(contract, project):
    from .source_revision_binding import binding
    binding(contract)
    if contract.get('family') != 'native_monitoring_section' or contract['domain'] != 'gitlab':
        raise ValueError('Only native Metrics navigation may declare this fixture')
    declaration = validate_declaration(dict(version=VERSION, project=project, from_level=10, to_level=20))
    value = deepcopy(contract)
    # Keep the navigation objective. Explicitly disclose the local access setup.
    goal = (value['original_goal'].rstrip() + ' In this local training environment, '
            f'the Metrics dashboard of {project} is enabled for project readers. '
            'Open the native Metrics page; no live metric values are required.')
    value.update(goal=goal, task_text_changed=True,
        goal_revision=dict(version=VERSION, original_goal=value['original_goal'], derived_goal=goal,
            reason='Disclose the local Metrics access setup while retaining the target navigation.',
            equivalent_to_original_goal=False),
        initial_state_revision=dict(version=VERSION, declaration=deepcopy(declaration),
            reason='Enable only target-project Metrics visibility before capturing a clean baseline.',
            equivalent_to_original_initial_state=False))
    value['public_parameters'].update(project=project, initial_metrics_visibility=declaration)
    value['public_task_input']['goal'] = goal
    value['public_task_input']['public_parameters'] = deepcopy(value['public_parameters'])
    value['public_task_input']['required_unresolved_public_parameters'] = [
        k for k, v in value['public_parameters'].items() if v is None]
    binding(value)
    return value


def declaration_for(contract):
    raw = contract.get('public_parameters', {}).get('initial_metrics_visibility')
    if raw is None:
        if contract.get('initial_state_revision', {}).get('version') == VERSION:
            raise ValueError('Private Metrics fixture cannot be hidden from public task input')
        return None
    declaration = validate_declaration(raw)
    revision = contract.get('initial_state_revision', {})
    if (contract.get('domain') != 'gitlab' or contract.get('family') != 'native_monitoring_section'
            or revision.get('version') != VERSION or revision.get('declaration') != declaration
            or revision.get('equivalent_to_original_initial_state') is not False
            or contract['public_parameters'].get('project') != declaration['project']
            or contract.get('public_task_input', {}).get('public_parameters') != contract['public_parameters']):
        raise ValueError('Public and private Metrics initial-state declarations must agree')
    return declaration


def feature_state(site):
    """All feature rows/columns, including unrelated projects, in stable order.

    This table is additional to the older sixteen-table native protection.
    The database computes one digest; no full-table JSON is repeatedly stored.
    """
    from .site_database import select_rows
    rows = select_rows(site, "SELECT COUNT(*) AS rows, md5(COALESCE(string_agg("
        "row_to_json(f)::text, E'\\n' ORDER BY f.id), '')) AS digest FROM project_features f")
    if (len(rows) != 1 or type(rows[0].get('rows')) is not int
            or rows[0]['rows'] < 1 or not re.fullmatch('[a-f0-9]{32}', rows[0].get('digest', ''))):
        raise ValueError('Complete native project-feature protection required')
    return rows[0]


def require_receipt(receipt, declaration, username):
    if (not isinstance(receipt, dict) or receipt.get('version') != VERSION
            or receipt.get('declaration') != declaration or receipt.get('username') != username
            or receipt.get('fixture_time') != FIXTURE_TIME
            or receipt.get('metrics_dashboard_authorized') is not True
            or receipt.get('other_feature_rows_unchanged') is not True
            or receipt.get('target_other_fields_unchanged') is not True
            or receipt.get('actor_is_admin') is not False
            or receipt.get('initializer_sha256') != hashlib.sha256(Path(__file__).with_suffix('.rb').read_bytes()).hexdigest()):
        raise ValueError('Current native Metrics fixture receipt required')
    return receipt


def require_prepared(site, contract, username):
    declaration = declaration_for(contract)
    if declaration is None:
        raise ValueError('Declared Metrics fixture required')
    receipt = require_receipt(getattr(site, 'prepared_metrics', None), declaration, username)
    if feature_state(site) != receipt['feature_state']:
        raise ValueError('Metrics baseline or other project features changed')
    return receipt


def prepare(site, username, declaration, directory):
    declaration = validate_declaration(declaration)
    if (getattr(site, 'domain', None) != 'gitlab' or not getattr(site, 'reuse_state', False)
            or getattr(site, 'generation', None) != 0 or getattr(site, 'stopped', True)
            or any(getattr(site, k, None) is not None for k in
                   ('prepared_initialization', 'prepared_hierarchy', 'prepared_metrics'))):
        raise ValueError('Metrics fixture requires a fresh reusable native site before any rollout')
    if not isinstance(username, str) or not username or len(username) > 255:
        raise ValueError('Explicit native actor account required')
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic(); ruby = Path(__file__).with_suffix('.rb')
    before = feature_state(site)
    with tempfile.TemporaryDirectory(prefix='metrics-fixture-', dir=site.state) as folder:
        folder = Path(folder)
        atomic_write_json(folder/'request.json', dict(declaration, username=username))
        (folder/'request.json').chmod(0o600)
        (folder/'initialize.rb').write_bytes(ruby.read_bytes())
        (folder/'initialize.rb').chmod(0o600)
        relative = '/state/' + folder.name
        native_command(site, ['bash', '/state/service.sh', 'gitlab-rails', 'env',
            'RAILS_ENV=production', 'LAB_METRICS_FIXTURE_REQUEST=' + relative + '/request.json',
            '/opt/gitlab/embedded/bin/bundle', 'exec',
            '/opt/gitlab/embedded/service/gitlab-rails/bin/rails', 'runner', '-e', 'production',
            relative + '/initialize.rb'], seconds=300)
        receipt = json.loads((folder/'receipt.json').read_text())
    receipt.update(declaration=declaration, initializer_sha256=hashlib.sha256(ruby.read_bytes()).hexdigest(),
        feature_state_before=before, feature_state=feature_state(site),
        native_controls_verified=False, training_admitted=False)
    require_receipt(receipt, declaration, username)
    if receipt['feature_state'] == before:
        raise ValueError('Declared visibility transition did not occur')
    atomic_write_json(directory/'initialization.json', receipt)
    site.stop_services(); site.snapshot.close()
    replacement_temp = tempfile.TemporaryDirectory(prefix='gitlab-metrics-baseline-', dir=site.state.parent)
    try:
        replacement = SiteStateSnapshot(site.state, Path(replacement_temp.name)/'state',
            services_stopped=lambda: site.stopped, restore_strategy=site.reset_strategy)
        replacement.save()
    except BaseException:
        replacement_temp.cleanup()
        raise
    previous = site.baseline_temp
    site.snapshot = replacement; site.baseline_temp = replacement_temp
    previous.cleanup(); site.prepared_metrics = receipt
    site.prepare_next_reset(); site.start_services()
    site.timed('prepare_metrics_baseline', started, profile=VERSION)
    return receipt
