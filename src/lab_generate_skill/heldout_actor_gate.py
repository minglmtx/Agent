"""Test-only pre-inference gate for native Reddit directory tasks.

This does not call or relax training admission. A packet binds independently
reviewed controls, source provenance, an explicit initialization review and the
exact native baseline. Native evidence alone never authorizes a model call.
"""
import gzip
import hashlib
import json
from pathlib import Path
import re
import tarfile
from urllib.parse import urlsplit

from .heldout_initial_controls import native_controls
from .heldout_initial_state import fingerprint

PROFILE = 'reddit-native-writable-thumbnail-cache-no-profiler-v1'
FAMILIES = {'reddit-browse-forum-directory-v1', 'reddit-alphabetical-forum-directory-v1', 'reddit-native-visible-form-v1'}
INITIAL_CHECKS = {'source_goal_and_start_bound', 'authentication_bound',
                  'visible_initial_state_reviewed', 'native_baseline_reproducible',
                  'public_private_boundary_reviewed'}


def pinned(ref):
    raw = Path(ref['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise ValueError('Pinned test evidence changed: ' + ref['path'])
    return raw


def local_url(url, origin):
    actual, expected = urlsplit(url), urlsplit(origin)
    if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
        return url
    return (actual.path or '/') + ('?' + actual.query if actual.query else '') + ('#' + actual.fragment if actual.fragment else '')


def initial_signature(page, origin):
    """Pin the declared native public baseline, not hidden answers or old bids.

    Keep every captured link, form value and rendered word. Only deployment
    origin and whitespace are normalized; timestamps are not silently removed.
    Source-to-native differences require the separate initialization review.
    """
    if page.get('native_profiler_surface') != {'toolbar_elements': 0, 'profiler_links': 0}:
        raise ValueError('A native initial capture without debugger surfaces is required')
    actual, expected = urlsplit(page['url']), urlsplit(origin)
    if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
        raise ValueError('Initial document left the declared native origin')
    normalize = lambda s: ' '.join(s.split())
    auth = page['source_authentication_check']
    if auth.get('passed') is not True or auth.get('expected') not in ('anonymous', 'authenticated'):
        raise ValueError('Verified initial authentication required')
    signature = dict(path=local_url(page['url'], origin), http_status=page['http_status'],
        title=normalize(page['title']), headings=[normalize(s) for s in page['heading_texts']],
        page_text=normalize(page['page_text']), authentication=auth,
        links=[dict(text=normalize(link['text']), href=local_url(link['href'], origin)) for link in page['local_links']],
        controls=sorted(native_controls(page['native_ax_nodes']), key=lambda c: json.dumps(c, sort_keys=True)))
    return fingerprint(signature)


def public_task(contract, initialization):
    """Project the task, never the private source/native comparison.

    An explicit derivative still needs an auditable initialization record.
    That record is for reviewers; the Actor observes the actual starting page.
    Legacy records named this text ``public_initialization``. The name does
    not authorize putting it into a model request.
    """
    if (contract.get('split') != 'test' or contract.get('heldout_quarantine') is not True
            or contract.get('eligible_for_training') is not False or contract.get('purpose') != 'codebase_acceptance'):
        raise ValueError('Explicit quarantined test contract required')
    return {key: contract[key] for key in ('task_id', 'domain', 'goal', 'start_path')}


def validate_initialization(review, source, contract, signatures, checkpoints):
    if (review.get('version') != 'heldout-initialization-review-v1'
            or review.get('status') != 'reviewed' or review.get('source_task_id') != source['source_task_id']
            or review.get('selected_trace_id') != source['selected_trace_id']
            or review.get('initial_observation_sha256') != source['initial_observation_sha256']):
        raise ValueError('Reviewed source-bound initialization required')
    if (review.get('native_initial_signature_sha256') != signatures[0] or len(set(signatures)) != 1
            or review.get('native_checkpoints') != checkpoints):
        raise ValueError('Initialization review differs from both actual cold captures')
    checks = review.get('checks', [])
    if (len(checks) != len(INITIAL_CHECKS) or {c['name'] for c in checks} != INITIAL_CHECKS
            or any(c.get('passed') is not True or not c.get('evidence_ref') or c.get('error') for c in checks)):
        raise ValueError('Every required initialization review check must have evidence')
    if contract['goal'] != source['goal'] or contract['start_path'] != source['start_path']:
        raise ValueError('This adapter preserves the literal original goal and start')
    if review['kind'] == 'original_observable_state':
        if contract['task_id'] != source['source_task_id'] or review.get('unresolved_differences'):
            raise ValueError('An original task cannot have unresolved initialization differences')
    elif review['kind'] == 'explicit_native_derivative':
        description = review.get('private_initialization_description', review.get('public_initialization'))
        if (not re.fullmatch(re.escape(source['source_task_id']) + r'--native-baseline-v[1-9][0-9]*', contract['task_id'])
                or review.get('derived_task_id') != contract['task_id'] or not review.get('reason')
                or not review.get('changes') or not isinstance(description, str) or not description.strip()):
            raise ValueError('An explicit derivative needs identity, rationale, differences and a private initialization description')
    else:
        raise ValueError('Unknown initialization provenance')


def load_packet(ref):
    packet = json.loads(pinned(ref))
    if (packet.get('version') != 'heldout-navigation-actor-packet-v1'
            or packet.get('purpose') != 'codebase_acceptance' or packet.get('formal_test_metric') is not False):
        raise ValueError('Test codebase Actor packet required')
    contract = json.loads(pinned(packet['contract']))
    initialization = json.loads(pinned(packet['initialization_review']))
    public = public_task(contract, initialization)
    if contract.get('domain') != 'reddit' or contract.get('native_content_profile') not in FAMILIES:
        raise ValueError('Reviewed native Reddit directory or form content required')
    if contract.get('environment_profile') != PROFILE:
        raise ValueError('The reviewed test environment profile is required')
    inventory = json.loads(pinned(packet['inventory']))
    if inventory.get('version') != 'test-engineering-inventory-v1' or inventory.get('isolation_conflicts') != []:
        raise ValueError('Reviewed isolated inventory required')
    inventory_root = Path(packet['inventory']['path']).parent
    tasks = [json.loads(s) for s in pinned(dict(path=str(inventory_root / 'tasks.jsonl'),
             sha256=inventory['artifacts']['tasks.jsonl']['sha256'])).splitlines()]
    if len(tasks) != 151 or len({t['source_task_id'] for t in tasks}) != 151 or any(t['split'] != 'test' for t in tasks):
        raise ValueError('Complete held-out inventory required')
    source = next(t for t in tasks if t['source_task_id'] == contract['source_task_id'])
    if (contract['selected_trace_id'] != source['selected_trace_id']
            or contract['initial_observation_sha256'] != source['initial_observation_sha256']):
        raise ValueError('Actor contract changed the selected original observation')
    plan = json.loads(pinned(packet['control_plan']))
    control_review = json.loads(pinned(packet['control_review']))
    if (plan['purpose'] != 'test_codebase_native_probe' or plan.get('disable_native_profiler') is not True
            or plan['capsule'] != packet['runtime_capsule']):
        raise ValueError('Control runtime or profile differs from Actor packet')
    workers = [r for r in control_review['reviews'] if r['plan'] == packet['control_plan']]
    if len(workers) != 1:
        raise ValueError('Exactly one independently reviewed native worker required')
    reviewed = [t for t in workers[0]['tasks'] if t['source_task_id'] == contract['source_task_id']]
    content_key = ('form_content_controls' if contract['native_content_profile'] == 'reddit-native-visible-form-v1'
                   else 'directory_content_controls')
    if (len(reviewed) != 2 or {r['cycle'] for r in reviewed} != {0, 1}
            or any(r.get('declared_controls_verified') is not True or
                   r.get('native_profiler_disabled_verified') is not True or
                   (r.get(content_key) or {}).get('passed') is not True for r in reviewed)):
        raise ValueError('Both native content control cycles must be independently verified')
    out = Path(plan['output']); receipt = json.loads((out / 'execution.json').read_text())
    if receipt['plan_sha256'] != packet['control_plan']['sha256'] or receipt['returncode'] != 0:
        raise ValueError('Actual control execution does not match its plan')
    if workers[0]['receipt']['archive_sha256'] != receipt['archive_sha256']:
        raise ValueError('Independent control review refers to a different archive')
    pinned(dict(path=str(out / 'evidence.tar.gz'), sha256=receipt['archive_sha256']))
    with tarfile.open(out / 'evidence.tar.gz') as archive:
        result = json.load(archive.extractfile('evidence/result.json'))
    if result['status'] != 'evidence_collected_pending_acceptance' or len(result['cycles']) != 2:
        raise ValueError('Two completed cold native cycles required')
    signatures, checkpoints, baselines = [], [], []
    for cycle in sorted(result['cycles'], key=lambda c: c['cycle']):
        if (cycle['complete13_before'] != cycle['complete13_after']
                or not cycle['service_processes_closed'] or not cycle['temporary_state_removed']):
            raise ValueError('Cold baseline integrity/closure failed')
        entry = next(t for t in cycle['tasks'] if t['source_task_id'] == contract['source_task_id'])
        checkpoint = entry['checkpoint']; raw = json.loads(gzip.decompress(pinned(checkpoint)))
        actual = raw['contract']
        for key in ('source_task_id', 'domain', 'goal', 'start_path', 'source_authentication',
                    'completion', 'native_content_profile', 'environment_profile',
                    'selected_trace_id', 'initial_observation_sha256', 'control_positive_paths', 'allow_initial_success'):
            if contract.get(key) != actual.get(key):
                raise ValueError('Actor binding changed a reviewed native condition: ' + key)
        proof_task = next(r for r in reviewed if r['cycle'] == cycle['cycle'])
        if proof_task['evidence'] != checkpoint:
            raise ValueError('Independent review used different task evidence')
        signatures.append(initial_signature(raw['cases']['initial_no_op'], cycle['site_origin']))
        checkpoints.append(checkpoint); baselines.append(cycle['complete13_before'])
    if baselines[0] != baselines[1]:
        raise ValueError('Independent control cold baselines differ')
    validate_initialization(initialization, source, contract, signatures, checkpoints)
    capsule = json.loads(pinned(packet['runtime_capsule']))
    return dict(packet=packet, contract=contract, public_task=public, initialization=initialization,
        initial_signature_sha256=signatures[0], protected_baseline=baselines[0],
        capsule=capsule, actor_attempt_authorized=True, evaluation_ready=False)
