"""Bounded reattempt for a proved terminal-capture defect, never actor failure.

The common repair authority verifies the old job, full archive, unchanged task,
source leases and original file pointers. This module qualifies the defect using
raw evidence. The ordinary admission check still recomputes current native proof.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit
from .answer_protocol_repair import pinned, plain, sha


def require_conflict(contract, index, values, review, record):
    if record.get('defect') == 'export_blocked_document_evidence':
        return require_export_block(contract, index, values, review, record)
    if record.get('defect') != 'gps_absent_map_document':
        raise ValueError('Unsupported terminal classification defect')
    sid = contract.get('source_task_id')
    result = values.get('result.json', {})
    trace = values.get('trajectory.json', {})
    terminal = values.get('gps-terminal.json', {})
    page = values.get('terminal-page.json', {})
    if (contract.get('domain') != 'map' or contract.get('candidate_completion', {}).get('family') != 'gps_overlay'
            or result.get('task_id') != contract['task_id'] or result.get('actor_attempts') != 1
            or result.get('error') is not None or result.get('evaluation', {}).get('status') != 'unknown'
            or result['evaluation'].get('reward') is not None
            or trace.get('task_instruction') != contract['goal'] or trace.get('error') is not None
            or not any(k.startswith('generation-') for k in values)):
        raise ValueError('Only an executed, exact, unscored GPS source may be repaired')
    if (terminal.get('native_terminal', 'missing') is not None or terminal.get('terminal') != page
            or terminal.get('judgment') != result['evaluation'] or terminal.get('integrity') is not True
            or terminal.get('capture_error') is not None or terminal.get('initial', {}).get('enabled') is not False
            or type(page.get('http_status')) is not int or not 200 <= page['http_status'] < 300
            or page.get('error_page') is not False or page.get('login_page') is not False
            or urlsplit(page.get('url', '')).path not in ('/communities', '/traces')):
        raise ValueError('Raw evidence does not demonstrate the absent-map classification defect')
    matches = [r for r in review.get('sources', []) if r.get('source_task_id') == sid]
    if len(matches) != 1:
        raise ValueError('Exact independent original review required')
    old = matches[0]
    if (old.get('task_id') != contract['task_id'] or old.get('outcome') != 'unknown'
            or old.get('attribution') != 'codebase_terminal_classification'
            or old.get('independent_judgment') != result['evaluation']
            or old.get('archive', {}).get('sha256') != index['archive_sha256']
            or old['archive'].get('members') != len(index['members'])):
        raise ValueError('Independent review does not match the raw unscored attempt')
    controls = json.loads(pinned(record['current_controls_review']))
    config = json.loads(pinned(record['current_proof_config']))
    candidates = json.loads(pinned(config['contracts']))['tasks']
    if (config['runtime_members'] != record['current_runtime_members']
            or controls.get('archive_sha256') != config['archive']['sha256']
            or [c for c in candidates if c.get('source_task_id') == sid] != [plain(contract)]):
        raise ValueError('Control review and current source proof must bind the same task and runtime')
    rows = [r for r in controls.get('sources', []) if r.get('source_task_id') == sid]
    if (controls.get('passed') is not True or controls.get('reset_and_cleanup_verified') is not True
            or len(rows) != 1 or rows[0].get('passed') is not True
            or rows[0].get('controls', {}).get('noop') != 'failure'
            or rows[0]['controls'].get('positive') != 'success'):
        raise ValueError('Repaired source requires independently reviewed native controls')
    shared = {k: v for row in controls['sources'] for k, v in row['controls'].items()}
    if any(shared.get(k) != 'failure' for k in ('communities', 'traces_list', '404', 'wrong_area')):
        raise ValueError('The affected non-map states must have actual negative controls')
    # These exact implementation bytes must have been tested in the controls,
    # and must differ from the old reader/evaluator that produced the unknown.
    current = json.loads(pinned(record['current_runtime_members']))
    old_members = json.loads(pinned(record['old_runtime_members']))
    project = Path(__file__).resolve().parents[2]
    for name in ('map_gps_overlay_observation', 'map_gps_overlay_terminal'):
        relative = 'src/lab_generate_skill/' + name + '.py'
        if (sha((project / relative).read_bytes()) != current[relative]['sha256']
                or current[relative]['sha256'] == old_members['runtime/' + relative]['sha256']):
            raise ValueError('Running GPS classification is not the validated repair')


def require_export_block(contract, index, values, review, record):
    from .map_export_runtime import require_admission
    from . import map_export_normal as normal
    result = values.get('result.json', {})
    trace = values.get('trajectory.json', {})
    page = values.get('terminal-page.json', {})
    transport = values.get('native-export-transport.json', {})
    if (contract.get('domain') != 'map' or contract.get('map_export', {}).get('kind') != 'osm_download'
            or result.get('task_id') != contract['task_id'] or result.get('actor_attempts') != 1
            or result.get('error') is not None or result.get('evaluation', {}).get('status') != 'unknown'
            or result['evaluation'].get('reward') is not None
            or result['evaluation'].get('reason') != 'Malformed terminal health'
            or trace.get('task_instruction') != contract['goal'] or trace.get('error') is not None
            or not any(k.startswith('generation-') for k in values)
            or page.get('url') != 'chrome-error://chromewebdata/' or page.get('http_status') is not None
            or page.get('error_page') is not True or page.get('login_page') is not False
            or 'navigation_policy_block' in page or transport.get('events') != [] or transport.get('faults') != []):
        raise ValueError('Exact unscored export and missing terminal policy evidence required')
    observed = []
    for key, step in values.items():
        if not key.startswith('step-'):
            continue
        obs = step.get('observation', {})
        if isinstance(obs, str): obs = json.loads(obs)
        block = obs.get('network_feedback', {})
        if (obs.get('url') == page['url'] and block.get('source') == 'local_network_policy'
                and block.get('reason') == 'outside_declared_local_services'
                and isinstance(block.get('blocked_origin'), str)):
            u = urlsplit(block['blocked_origin'])
            if u.scheme in ('http', 'https') and u.netloc:
                observed.append(block)
    if not observed:
        raise ValueError('An actor assertion cannot replace recorded network-policy feedback')
    rows = [r for r in review.get('sources', []) if r.get('source_task_id') == contract['source_task_id']]
    if (len(rows) != 1 or rows[0].get('task_id') != contract['task_id'] or rows[0].get('valid_result') is not False
            or rows[0].get('attribution') != 'actor_navigation_and_codebase_terminal_classification'
            or rows[0].get('independent_judgment') != result['evaluation']
            or rows[0].get('archive', {}).get('sha256') != index['archive_sha256']
            or rows[0]['archive'].get('members') != len(index['members'])):
        raise ValueError('Exact independent export defect review required')
    proof = json.loads(pinned(record['native_proof']))
    controls = json.loads(pinned(record['current_controls_review']))
    if (controls.get('passed') is not True or controls.get('source_task_id') != contract['source_task_id']
            or controls.get('task_id') != contract['task_id'] or controls.get('reset_and_cleanup_verified') is not True
            or controls.get('proof_sha256') != record['native_proof']['sha256']):
        raise ValueError('The existing complete native export proof must remain bound')
    require_admission(contract, proof)
    integration = json.loads(pinned(record['repair_integration_review']))
    required = ('src/lab_generate_skill/browser_request_policy.py',
                'src/lab_generate_skill/map_export_normal.py', 'scripts/run_site_navigation_once.py')
    project = Path(__file__).resolve().parents[2]
    if (integration.get('ordinary_session_terminal_capture_passed') is not True
            or integration.get('unclassified_transport_retains_unknown') is not True
            or integration.get('real_browser_verified') is not True):
        raise ValueError('Actual ordinary-session policy capture validation required')
    for relative in required:
        if sha((project/relative).read_bytes()) != integration.get('files', {}).get(relative):
            raise ValueError('Current export repair differs from tested ordinary session')
    # Check the minimal distinguishing evidence against the running evaluator.
    origin = 'http://local.invalid'
    patched = dict(page, navigation_policy_block=dict(observed[-1], document_url=page['url']))
    if normal._health(patched, origin) != {'correct_site': False, 'page_valid': False}:
        raise ValueError('Policy-block classification repair is absent')
    try:
        normal._health(page, origin)
    except ValueError:
        pass
    else:
        raise ValueError('Unclassified transport errors must not be coerced to model failure')
