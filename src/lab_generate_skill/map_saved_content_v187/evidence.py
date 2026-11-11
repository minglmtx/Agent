"""Recompute qualified native controls and ordinary lifecycle from sealed bytes."""
from pathlib import PurePosixPath
from urllib.parse import urlsplit
import hashlib, json
from .save_judge import evaluate as current_evaluate, snapshot
from .save_capture import witnessed
from .save_protection import check
from .save_snapshot import source as snapshot_source
from lab_generate_skill.map_existing_account_observation import require_anonymous


def parsed(archive, name):
    return json.loads(archive[name])


def native_value(archive, folder, label, original_script_sha):
    value = snapshot(parsed(archive, folder + '/native-' + label + '.json'))
    receipt = parsed(archive, folder + '/native-' + label + '-receipt.json')
    if not receipt['read_only'] or receipt['script_sha256'] != original_script_sha or receipt['command'][-3:-1] != ['rails', 'runner']:
        raise ValueError('Original readonly native receipt differs')
    parts = PurePosixPath(receipt['raw_log']).parts
    log = archive['/'.join(parts[parts.index('native') + 1:])]
    if hashlib.sha256(log).hexdigest() != receipt['raw_log_sha256']:
        raise ValueError('Raw native readout changed')
    rows = [json.loads(line) for line in log.decode().splitlines() if line.startswith('{') and '"read_only"' in line]
    if rows != [value]:
        raise ValueError('Native snapshot not bound to actual Rails readout')
    return value


def replay(contracts, archives, baseline, native_review, ordinary_review, original_script_sha):
    scores = {}
    selection = [('upload_retained', 'upload', ('noop', 'unsaved', 'wrong_author', 'positive')),
                 ('diary_retained', 'diary', ('noop', 'unsaved')),
                 ('native_final', 'diary', ('wrong_author', 'positive'))]
    for group, kind, modes in selection:
        archive = archives[group]
        report = parsed(archive, 'result.json')
        if any(report[k] != 0 for k in ('actor_calls', 'model_loads', 'training_admissions')):
            raise ValueError('Controls must remain separate from Actor executions')
        for mode in modes:
            label = kind + '-' + mode
            contract = contracts[kind]
            row = parsed(archive, label + '/result.json')
            if row != report['cases'][label]:
                raise ValueError('Control result differs from archive index')
            if kind == 'upload' and mode == 'positive':
                if row['passed'] is not False or row['evaluation_status'] != 'unknown':
                    raise ValueError('Original filename-judge failure must remain preserved')
            elif row['passed'] is not True:
                raise ValueError('Unqualified retained native control')
            before = native_value(archive, label, label + '-before', original_script_sha)
            after = native_value(archive, label, label + '-after', original_script_sha)
            native_value(archive, label, label + '-final', original_script_sha)
            views = [parsed(archive, name) for name in sorted(archive) if name.startswith(label + '/probe/view-') and name.endswith('.json')]
            steps = [parsed(archive, name) for name in sorted(archive) if name.startswith(label + '/browser/step-') and name.endswith('.json')]
            if not views or len(views) != len(steps):
                raise ValueError('Native control public observations incomplete')
            health = parsed(archive, label + '/browser/initial-page-health.json')
            u = urlsplit(health['url'])
            origin = u.scheme + '://' + u.netloc
            if health['http_status'] != 200 or health['error_page'] or health['login_page'] or health['url'] != origin + contract['start_path']:
                raise ValueError('Original control start differs')
            bodies = []
            for index, (view, step) in enumerate(zip(views, steps)):
                if view['index'] != index or step['step'] != index or view['goal'] != contract['goal']:
                    raise ValueError('Public control input is not source bound')
                body = json.loads(view['messages'][-1]['content'])
                if body['goal'] != contract['goal'] or body['url'] != step['observation']['url']:
                    raise ValueError('Serialized native input differs')
                bodies.append(body)
            witness = witnessed(kind, contract, bodies, parsed(archive, label + '/browser/save-index.json'))
            if witness != parsed(archive, label + '/witness.json'):
                raise ValueError('Actual public save/readback witness differs')
            terminal = parsed(archive, label + '/browser/terminal-page.json')
            score = evaluate(kind, before, after, contract, witness, terminal, origin)
            if score['status'] != ('success' if mode == 'positive' else 'failure') or score != native_review['cases'][label]['judgment']:
                raise ValueError('Native positive/negative judgment changed')
            uid = next(u['id'] for u in before['users'] if u['email'] == contract['parameters']['account']['email'])
            key = 'traces' if kind == 'upload' else 'diaries'
            old = {r['id'] for r in before[key]}
            created = [r for r in after[key] if r['id'] not in old]
            if mode in ('noop', 'unsaved'):
                if created:
                    raise ValueError('No-save control unexpectedly created a record')
            elif len(created) != 1 or (created[0]['user_id'] == uid) != (mode == 'positive'):
                raise ValueError('Native wrong-author/positive control is not distinct')
            scores[label] = score
    final = archives['native_final']
    final_result = parsed(final, 'result.json')
    if not final_result['passed'] or not final_result['full_cold_restore_verified'] or not final_result['dirty_reuse_refused']:
        raise ValueError('Native full cold reset incomplete')
    for archive, folders in [(final, ('controls', 'cold-reset')),
                             (archives['upload_retained'], ('controls',)),
                             (archives['diary_retained'], ('controls',))]:
        for folder in folders:
            if parsed(archive, folder + '/full-fingerprint.json') != baseline:
                raise ValueError('Complete original baselines differ')
    if parsed(final, 'controls/complete-native-state.json') != parsed(final, 'cold-reset/complete-native-state.json'):
        raise ValueError('Full native rows/sequences not restored')
    for folder in ('controls', 'cold-reset'):
        closure = parsed(final, folder + '/closure.json')
        if not all(closure[k] is True for k in ('passed', 'state_removed', 'ports_released')):
            raise ValueError('Native writer closure incomplete')

    archive = archives['ordinary']
    report = parsed(archive, 'result.json')
    if not report['passed'] or not report['common_site_worker'] or not report['common_session']:
        raise ValueError('Ordinary source lifecycle not qualified')
    ordinary_scores = {}
    for kind, contract in contracts.items():
        browser = kind + '/browser/'
        if parsed(archive, kind + '/full-fingerprint.json') != baseline:
            raise ValueError('Ordinary original baseline differs')
        values = {}
        for label in ('save-before', 'save-after'):
            value = snapshot(parsed(archive, browser + label + '.json'))
            receipt = parsed(archive, browser + label + '-receipt.json')
            raw = archive[browser + label + '.log']
            if not receipt['read_only'] or not receipt['all_public_table_triggers'] or receipt['source_sha256'] != hashlib.sha256(snapshot_source().encode()).hexdigest() or receipt['raw_sha256'] != hashlib.sha256(raw).hexdigest():
                raise ValueError('Extended readonly save snapshot differs')
            if [json.loads(line) for line in raw.decode().splitlines() if line.startswith('{') and '"read_only"' in line] != [value]:
                raise ValueError('Extended raw native readout differs')
            values[label] = value
        before, after = values['save-before'], values['save-after']
        files_before = parsed(archive, browser + 'save-before-files.json')
        files_after = parsed(archive, browser + 'save-after-files.json')
        if before['protection']['guard'] != baseline['database'] or files_before != baseline['files'] or before['diaries'] or before['traces']:
            raise ValueError('Ordinary task did not start from empty declared targets')
        protection = check(kind, before['protection'], after['protection'], files_before=files_before, files_after=files_after)
        receipt = parsed(archive, browser + 'save-terminal.json')
        if protection != receipt['protection'] or not protection['passed'] or receipt['capture_error'] is not None or receipt['integrity'] is not True:
            raise ValueError('Complete native save protection failed')
        row = report['cases'][kind]
        initial = parsed(archive, browser + 'save-initial.json')
        if initial['original_start']['url'] != row['site_origin'] + contract['start_path']:
            raise ValueError('Ordinary original start differs')
        require_anonymous(initial['session'], row['site_origin'])
        views = [parsed(archive, name) for name in sorted(archive) if name.startswith(kind + '/probe/view-') and name.endswith('.json')]
        issued = parsed(archive, browser + 'save-issued.json')
        bodies = [json.loads(v['messages'][-1]['content']) for v in views]
        actual_issued = {str(i): [b['observation']] for i, b in enumerate(bodies)}
        if len(views) != row['actual_public_views'] or actual_issued != issued['issued']:
            raise ValueError('Ordinary actual public acknowledgement differs')
        if any(b['goal'] != contract['goal'] for b in bodies):
            raise ValueError('Ordinary public goal differs')
        witness = witnessed(kind, contract, bodies, parsed(archive, browser + 'save-index.json'))
        if witness != receipt['witness']:
            raise ValueError('Ordinary save/readback witness differs')
        terminal = parsed(archive, browser + 'terminal-page.json')
        score = evaluate(kind, before, after, contract, witness, terminal, row['site_origin'])
        if score != receipt['judgment'] or score != row['judgment'] or score != ordinary_review['cases'][kind]['judgment'] or score['status'] != 'success':
            raise ValueError('Ordinary saved-content judgment changed')
        events = receipt['events']
        if events != row['lifecycle'] or events[:3] != ['prepare', 'attach', 'observe_initial'] or events[-4:] != ['capture_terminal', 'close', 'provide_trace', 'score_terminal'] or events.count('record') != len(views) or events.count('acknowledge_issued') != len(views):
            raise ValueError('Ordinary lifecycle incomplete')
        if not row['dirty_reuse_refused']:
            raise ValueError('Ordinary dirty state was reusable')
        ordinary_scores[kind] = score
    cold = parsed(archive, 'ordinary-cold-rebuild.json')
    if cold != dict(passed=True, previous_state_removed=True, new_instance_index=2, via_common_site_worker=True):
        raise ValueError('Common SiteWorker cold rebuild differs')
    closure = parsed(archive, 'closure.json')
    if not all(closure[k] is True for k in ('passed', 'state_removed', 'ports_released')):
        raise ValueError('Ordinary closure incomplete')
    return dict(passed=True, native_controls=scores, ordinary_controls=ordinary_scores,
                full_cold_reset_verified=True, actual_public_input_verified=True)


def evaluate(*args, **kwargs):
    """Compare current closed-control outcomes in their original saved schema."""
    result = dict(current_evaluate(*args, **kwargs))
    if result['version'] != 'native-map-upload-diary-save-v187-r5':
        raise ValueError('Explicit reviewed saved-content verdict revision required')
    result['version'] = 'native-map-upload-diary-save-v187-r4'
    if result['status'] == 'success':
        result['reason'] = 'Native saved record and actual public readback checked; rendering, per-point audit and future interaction are outside scope.'
    return result
