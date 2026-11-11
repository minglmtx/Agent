"""Recompute qualified native and ordinary evidence without another website.

Receipt token counts were independently recounted in the sealed qualification;
this gate replays the same protocol and binds every receipt to actual messages.
"""
from pathlib import PurePosixPath
from fnmatch import fnmatchcase
from urllib.parse import urlsplit
import hashlib, json
from .rss_client import evaluate as current_evaluate_rss, parse_rss, STATE_VERSION as RSS_VERSION
from .diary_read import evaluate as evaluate_ny
from .reader_ui import rack_initializer
from .profile import declared_profile
from lab_generate_skill.runtime_profile import actor_protocol
from lab_generate_skill.observation_budget import fit_actor_messages
from lab_generate_skill.map_reset_guard import checked_state
from lab_generate_skill.map_existing_account_observation import require_anonymous


def members(archive, folder, pattern):
    return sorted(PurePosixPath(n) for n in archive if PurePosixPath(n).parent == folder
                  and fnmatchcase(PurePosixPath(n).name, pattern))


def receipt_count(view, receipts, messages):
    rows = view['token_counts']
    if len(receipts) >= len(rows):
        raise ValueError('Missing independently recounted tokenizer receipt')
    row = rows[len(receipts)]
    if row['messages'] != messages or type(row['tokens']) is not int or row['tokens'] <= 0:
        raise ValueError('Tokenizer receipt belongs to another actual public input')
    receipts.append(dict(messages=messages, tokens=row['tokens']))
    return row['tokens']


def native_controls(contracts, archive, baseline, qualified_review, expected_report):
    read = lambda p: json.loads(archive[str(p)])
    closed = PurePosixPath('.')
    fixture = declared_profile()
    report = read(closed / 'result.json')
    if not (report == expected_report and report['passed']):
        raise ValueError("Closed reader evidence mismatch: report == expected_report and report['passed']")
    if not report['actor_calls'] == report['model_loads'] == report['training_admissions'] == 0:
        raise ValueError("Closed reader evidence mismatch: report['actor_calls'] == report['model_loads'] == report['training_admissions'] == 0")
    if not report['private_native_factory_starts'] == 2:
        raise ValueError("Closed reader evidence mismatch: report['private_native_factory_starts'] == 2")
    if not (report['full_cold_restore_verified'] and report['dirty_reader_reuse_refused']):
        raise ValueError("Closed reader evidence mismatch: report['full_cold_restore_verified'] and report['dirty_reader_reuse_refused']")
    if not baseline == read(closed / 'controls/full-fingerprint.json'):
        raise ValueError("Closed reader evidence mismatch: baseline == read(closed / 'controls/full-fingerprint.json')")
    if not baseline == read(closed / 'cold-reset/full-fingerprint.json'):
        raise ValueError("Closed reader evidence mismatch: baseline == read(closed / 'cold-reset/full-fingerprint.json')")
    if not baseline['reader']['logical']['records'] == []:
        raise ValueError("Closed reader evidence mismatch: baseline['reader']['logical']['records'] == []")

    def native_snapshot(value):
        state = checked_state(value['database'])
        if not state['changed'] == []:
            raise ValueError("Closed reader evidence mismatch: state['changed'] == []")
        payload = dict(baseline=value['baseline'], database=state, files=value['files'])
        if not hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest() == value['native_fingerprint']:
            raise ValueError("Closed reader evidence mismatch: hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest() == value['native_fingerprint']")
        if not len(value['diaries']) == len(fixture['diaries']) == 2:
            raise ValueError("Closed reader evidence mismatch: len(value['diaries']) == len(fixture['diaries']) == 2")
        for spec in fixture['diaries']:
            rows = [r for r in value['diaries'] if all((r[k] == spec[k] for k in ('title', 'body', 'latitude', 'longitude')))]
            if not (len(rows) == 1 and rows[0]['visible'] is True):
                raise ValueError("Closed reader evidence mismatch: len(rows) == 1 and rows[0]['visible'] is True")
            if not rows[0]['author'] == fixture['account']['display_name']:
                raise ValueError("Closed reader evidence mismatch: rows[0]['author'] == fixture['account']['display_name']")
        return value
    native_snapshot(baseline['native'])
    for cycle in ('controls', 'cold-reset'):
        folder = closed / cycle
        closure = read(folder / 'closure.json')
        if not all((closure[k] is True for k in ('passed', 'state_removed', 'ports_released', 'reader_threads_joined'))):
            raise ValueError("Closed reader evidence mismatch: all((closure[k] is True for k in ('passed', 'state_removed', 'ports_released', 'reader_threads_joined')))")
        ext = read(folder / 'site/local-reader-extension.json')
        if not (ext['explicit_environment_derivative'] and ext['installed_before_guard']):
            raise ValueError("Closed reader evidence mismatch: ext['explicit_environment_derivative'] and ext['installed_before_guard']")
        if not (ext['native_feed_interception'] is False and ext['original_benchmark_equivalence'] is False):
            raise ValueError("Closed reader evidence mismatch: ext['native_feed_interception'] is False and ext['original_benchmark_equivalence'] is False")
        if not ext['source_sha256'] == hashlib.sha256(rack_initializer(ext['reader_port']).encode()).hexdigest():
            raise ValueError("Closed reader evidence mismatch: ext['source_sha256'] == hashlib.sha256(rack_initializer(ext['reader_port']).encode()).hexdigest()")
        clone = read(folder / 'site/app-clone-progress.json')
        if not (clone['status'] == 'complete' and clone['source_modified'] is False and (clone['hardlinks_used'] is False)):
            raise ValueError("Closed reader evidence mismatch: clone['status'] == 'complete' and clone['source_modified'] is False and (clone['hardlinks_used'] is False)")
        if not (clone['completed_files'] == clone['total_files'] and clone['completed_bytes'] == clone['total_bytes']):
            raise ValueError("Closed reader evidence mismatch: clone['completed_files'] == clone['total_files'] and clone['completed_bytes'] == clone['total_bytes']")
        overlap = [r for r in read(folder / 'site/progress.json') if r['phase'] == 'clone_app_geographic_database_overlap']
        if not (len(overlap) == 1 and overlap[0]['returncode'] == 0):
            raise ValueError("Closed reader evidence mismatch: len(overlap) == 1 and overlap[0]['returncode'] == 0")
        if not (overlap[0]['same_original_clone_command'] and overlap[0]['postgres_start_waited_for_complete_copy']):
            raise ValueError("Closed reader evidence mismatch: overlap[0]['same_original_clone_command'] and overlap[0]['postgres_start_waited_for_complete_copy']")
        declared = read(folder / 'site/declared-local-diaries.json')
        if not (declared['synthetic_content'] and declared['original_benchmark_equivalence'] is False):
            raise ValueError("Closed reader evidence mismatch: declared['synthetic_content'] and declared['original_benchmark_equivalence'] is False")
        if not declared['records'] == baseline['native']['diaries']:
            raise ValueError("Closed reader evidence mismatch: declared['records'] == baseline['native']['diaries']")
    cases = {}
    labels = [('rss', mode) for mode in ('noop', 'filled_unsaved', 'wrong_feed', 'positive_empty_native_feed', 'preexisting_subscription')]
    labels += [('ny', mode) for mode in ('noop', 'wrong_region_detail', 'positive_list', 'positive_detail')]
    if not set(report['cases']) == {kind + '-' + mode for (kind, mode) in labels}:
        raise ValueError("Closed reader evidence mismatch: set(report['cases']) == {kind + '-' + mode for (kind, mode) in labels}")
    previous_reader = baseline['reader']
    for (kind, mode) in labels:
        label = kind + '-' + mode
        (folder, contract) = (closed / label, contracts[kind])
        browser = folder / 'browser'
        row = read(folder / 'result.json')
        if not (row == report['cases'][label] and row['passed'] and (row['actor_calls'] == 0)):
            raise ValueError("Closed reader evidence mismatch: row == report['cases'][label] and row['passed'] and (row['actor_calls'] == 0)")
        (before_native, after_native) = (read(folder / 'before-native.json'), read(folder / 'after-native.json'))
        if not native_snapshot(before_native) == native_snapshot(after_native) == baseline['native']:
            raise ValueError("Closed reader evidence mismatch: native_snapshot(before_native) == native_snapshot(after_native) == baseline['native']")
        (before, after) = (read(folder / 'before-reader.json'), read(folder / 'after-reader.json'))
        if not before == previous_reader:
            raise ValueError('Closed reader evidence mismatch: before == previous_reader')
        previous_reader = after
        for state in (before, after):
            logical = state['logical']
            if not (logical['version'] == RSS_VERSION and logical['schema'] == baseline['reader']['logical']['schema']):
                raise ValueError("Closed reader evidence mismatch: logical['version'] == RSS_VERSION and logical['schema'] == baseline['reader']['logical']['schema']")
            for saved in logical['records']:
                body = bytes.fromhex(saved['body_hex'])
                if not (saved['body_sha256'] == hashlib.sha256(body).hexdigest() and saved['parsed'] == parse_rss(body)):
                    raise ValueError("Closed reader evidence mismatch: saved['body_sha256'] == hashlib.sha256(body).hexdigest() and saved['parsed'] == parse_rss(body)")
        views = [read(p) for p in members(archive, folder / 'probe', 'view-*.json')]
        steps = [read(p) for p in members(archive, browser, 'step-*.json')]
        captures = read(folder / 'captures.json')
        if not len(views) == len(steps) == len(captures) == row['views']:
            raise ValueError("Closed reader evidence mismatch: len(views) == len(steps) == len(captures) == row['views']")
        (health, initial) = (read(browser / 'initial-page-health.json'), read(folder / 'original-initial.json'))
        parts = urlsplit(health['url'])
        origin = parts.scheme + '://' + parts.netloc
        if not origin == row['site_origin']:
            raise ValueError("Closed reader evidence mismatch: origin == row['site_origin']")
        if not health['url'] == initial['url'] == steps[0]['observation']['url'] == origin + contract['start_path']:
            raise ValueError("Closed reader evidence mismatch: health['url'] == initial['url'] == steps[0]['observation']['url'] == origin + contract['start_path']")
        if not (health['http_status'] == 200 and health['error_page'] is False and (health['login_page'] is False)):
            raise ValueError("Closed reader evidence mismatch: health['http_status'] == 200 and health['error_page'] is False and (health['login_page'] is False)")
        (observations, total_tokens) = ([], 0)
        for (i, (view, step, capture)) in enumerate(zip(views, steps, captures)):
            if not view['index'] == step['step'] == capture['step'] == i:
                raise ValueError("Closed reader evidence mismatch: view['index'] == step['step'] == capture['step'] == i")
            if not (view['goal'] == contract['goal'] and view['history'] == []):
                raise ValueError("Closed reader evidence mismatch: view['goal'] == contract['goal'] and view['history'] == []")
            if not view['observation'] == step['observation']:
                raise ValueError("Closed reader evidence mismatch: view['observation'] == step['observation']")
            if not capture == read(browser / f'view-capture-{i:03d}.json'):
                raise ValueError("Closed reader evidence mismatch: capture == read(browser / f'view-capture-{i:03d}.json')")
            receipts = []

            def count(messages):
                return receipt_count(view, receipts, messages)
            protocol = actor_protocol()
            prepared = protocol.prepare_observation(contract['goal'], step['observation'], [], token_counter=count, skills=[])
            messages = protocol.messages(contract['goal'], prepared, [], skills=[])
            (sent, budget) = fit_actor_messages(messages, count, 16384)
            if not (messages == view['protocol_messages'] and sent == view['messages']):
                raise ValueError("Closed reader evidence mismatch: messages == view['protocol_messages'] and sent == view['messages']")
            if not (budget == view['observation_budget'] and receipts == view['token_counts']):
                raise ValueError("Closed reader evidence mismatch: budget == view['observation_budget'] and receipts == view['token_counts']")
            total_tokens += len(receipts)
            public = json.loads(sent[-1]['content'])
            if not (public['goal'] == contract['goal'] and public['url'] == capture['state']['url']):
                raise ValueError("Closed reader evidence mismatch: public['goal'] == contract['goal'] and public['url'] == capture['state']['url']")
            observations.append(dict(capture['state'], actual_public_text=public['observation']))
        (events, terminal) = (read(folder / 'reader-events.json'), read(browser / 'terminal-page.json'))
        private = read(folder / 'native-diary-reference.json')
        ny = next((s for s in fixture['diaries'] if s['region'] == 'New York City'))
        expected = [dict(r, region='New York City') for r in baseline['native']['diaries'] if r['title'] == ny['title']]
        if not private == dict(entries=expected):
            raise ValueError('Closed reader evidence mismatch: private == dict(entries=expected)')
        if kind == 'rss':
            responses = [dict({k: v for (k, v) in r.items() if k != 'body_hex'}, body=bytes.fromhex(r['body_hex'])) for e in events for r in e.get('responses', [])]
            requests = [e for e in events if e['event'] == 'subscription_request']
            if not not any((e['event'] == 'request_error' for e in events)):
                raise ValueError("Closed reader evidence mismatch: not any((e['event'] == 'request_error' for e in events))")
            if mode in ('noop', 'filled_unsaved'):
                if not (requests == [] and before == after):
                    raise ValueError('Closed reader evidence mismatch: requests == [] and before == after')
            else:
                if not (len(requests) == 1 and requests[0]['before'] == before['logical'] and (requests[0]['after'] == after['logical'])):
                    raise ValueError("Closed reader evidence mismatch: len(requests) == 1 and requests[0]['before'] == before['logical'] and (requests[0]['after'] == after['logical'])")
                if not len(responses) == 1:
                    raise ValueError('Closed reader evidence mismatch: len(responses) == 1')
                expected_path = '/diary/rss' if mode == 'wrong_feed' else '/traces/rss'
                if not responses[0]['url'] == responses[0]['requested_url'] == origin + expected_path:
                    raise ValueError("Closed reader evidence mismatch: responses[0]['url'] == responses[0]['requested_url'] == origin + expected_path")
                if not parse_rss(responses[0]['body'])['entries'] == (2 if mode == 'wrong_feed' else 0):
                    raise ValueError("Closed reader evidence mismatch: parse_rss(responses[0]['body'])['entries'] == (2 if mode == 'wrong_feed' else 0)")
            issued = [o for o in observations if o['url'] == terminal['url']]
            last = issued[-1] if issued else dict(ids=[], actual_public_text='')
            reopened = dict(url=terminal['url'], http_status=terminal['http_status'], error=terminal['error_page'], method='GET' if any((e['event'] == 'reader_reopened' for e in events)) else None, visible_subscription_ids=last['ids'], actual_public_text=last['actual_public_text'])
            if not reopened == read(folder / 'reader-reopened-witness.json'):
                raise ValueError("Closed reader evidence mismatch: reopened == read(folder / 'reader-reopened-witness.json')")
            judgment = evaluate_rss(before['logical'], after['logical'], origin=origin, responses=responses, reopened=reopened)
            if mode == 'preexisting_subscription':
                if not before == after:
                    raise ValueError('Closed reader evidence mismatch: before == after')
        else:
            if not (before == after and (not events)):
                raise ValueError('Closed reader evidence mismatch: before == after and (not events)')
            judgment = evaluate_ny(private, observations, terminal, origin=origin, native_unchanged=True)
        if not judgment == read(folder / 'judgment.json') == row['judgment']:
            raise ValueError("Closed reader evidence mismatch: judgment == read(folder / 'judgment.json') == row['judgment']")
        if not judgment['status'] == ('success' if mode.startswith('positive') else 'failure'):
            raise ValueError("Closed reader evidence mismatch: judgment['status'] == ('success' if mode.startswith('positive') else 'failure')")
        cases[label] = dict(passed=True, source_task_id=contract['source_task_id'], judgment=judgment, actual_public_views_reconstructed=len(views), tokenizer_receipts_recounted=total_tokens, complete_native_read_only_state_verified=True, actor_calls=0)
    if not cases == qualified_review['cases']:
        raise ValueError("Closed reader evidence mismatch: cases == qualified_review['cases']")
    return {k: v['judgment'] for (k, v) in cases.items()}


def ordinary_controls(contracts, archive, baseline, qualified_review, expected_report):
    read = lambda p: json.loads(archive[str(p)])
    closed = PurePosixPath('.')
    fixture = declared_profile()
    report = read(closed / 'result.json')
    if not (report == expected_report and report['passed']):
        raise ValueError("Closed reader evidence mismatch: report == expected_report and report['passed']")
    if not report['actor_calls'] == report['model_loads'] == report['training_admissions'] == 0:
        raise ValueError("Closed reader evidence mismatch: report['actor_calls'] == report['model_loads'] == report['training_admissions'] == 0")
    if not (report['common_site_worker'] and report['common_session'] and (set(report['cases']) == {'ny', 'rss'})):
        raise ValueError("Closed reader evidence mismatch: report['common_site_worker'] and report['common_session'] and (set(report['cases']) == {'ny', 'rss'})")
    cases = {}
    origins = []
    for kind in ('ny', 'rss'):
        (folder, contract) = (closed / kind, contracts[kind])
        browser = folder / 'browser'
        row = read(folder / 'result.json')
        if not (row == report['cases'][kind] and row['passed']):
            raise ValueError("Closed reader evidence mismatch: row == report['cases'][kind] and row['passed']")
        before = read(browser / 'reader-native-before.json')
        after = read(browser / 'reader-native-after.json')
        if not before == read(folder / 'full-fingerprint.json') == baseline:
            raise ValueError("Closed reader evidence mismatch: before == read(folder / 'full-fingerprint.json') == baseline")
        if not before['native'] == after['native']:
            raise ValueError("Closed reader evidence mismatch: before['native'] == after['native']")
        if not before['reader']['logical']['records'] == []:
            raise ValueError("Closed reader evidence mismatch: before['reader']['logical']['records'] == []")
        private = dict(entries=[])
        for spec in fixture['diaries']:
            matched = [r for r in before['native']['diaries'] if all((r[k] == spec[k] for k in ('title', 'body', 'latitude', 'longitude')))]
            if not (len(matched) == 1 and matched[0]['visible'] is True and (matched[0]['author'] == fixture['account']['display_name'])):
                raise ValueError("Closed reader evidence mismatch: len(matched) == 1 and matched[0]['visible'] is True and (matched[0]['author'] == fixture['account']['display_name'])")
            if spec['region'] == 'New York City':
                private['entries'].append(dict(matched[0], region=spec['region']))
        if not private == read(browser / 'native-diary-reference.json'):
            raise ValueError("Closed reader evidence mismatch: private == read(browser / 'native-diary-reference.json')")
        (health, initial) = (read(browser / 'initial-page-health.json'), read(browser / 'reader-initial.json'))
        origin = row['site_origin']
        origins.append(origin)
        if not health['url'] == initial['original_start']['url'] == origin + contract['start_path']:
            raise ValueError("Closed reader evidence mismatch: health['url'] == initial['original_start']['url'] == origin + contract['start_path']")
        if not (health['http_status'] == 200 and health['error_page'] is False and (health['login_page'] is False)):
            raise ValueError("Closed reader evidence mismatch: health['http_status'] == 200 and health['error_page'] is False and (health['login_page'] is False)")
        require_anonymous(initial['session'], origin)
        views = [read(p) for p in members(archive, folder / 'probe', 'view-*.json')]
        steps = [read(p) for p in members(archive, browser, 'step-*.json')]
        captures = [read(p) for p in members(archive, browser, 'reader-capture-*.json')]
        issued = read(browser / 'reader-issued.json')
        if not len(views) == len(steps) == len(captures) == row['actual_public_views']:
            raise ValueError("Closed reader evidence mismatch: len(views) == len(steps) == len(captures) == row['actual_public_views']")
        if not captures == issued['captures']:
            raise ValueError("Closed reader evidence mismatch: captures == issued['captures']")
        (observations, tokens) = ([], 0)
        for (i, (view, step, capture)) in enumerate(zip(views, steps, captures)):
            if not view['index'] == step['step'] == capture['step'] == i:
                raise ValueError("Closed reader evidence mismatch: view['index'] == step['step'] == capture['step'] == i")
            if not (view['goal'] == contract['goal'] and view['history'] == []):
                raise ValueError("Closed reader evidence mismatch: view['goal'] == contract['goal'] and view['history'] == []")
            if not view['observation'] == step['observation']:
                raise ValueError("Closed reader evidence mismatch: view['observation'] == step['observation']")
            receipts = []

            def count(messages):
                return receipt_count(view, receipts, messages)
            protocol = actor_protocol()
            prepared = protocol.prepare_observation(contract['goal'], step['observation'], [], token_counter=count, skills=[])
            messages = protocol.messages(contract['goal'], prepared, [], skills=[])
            (sent, budget) = fit_actor_messages(messages, count, 16384)
            if not (messages == view['protocol_messages'] and sent == view['messages']):
                raise ValueError("Closed reader evidence mismatch: messages == view['protocol_messages'] and sent == view['messages']")
            if not (budget == view['observation_budget'] and receipts == view['token_counts']):
                raise ValueError("Closed reader evidence mismatch: budget == view['observation_budget'] and receipts == view['token_counts']")
            body = json.loads(sent[-1]['content'])
            if not (body['goal'] == contract['goal'] and body['url'] == capture['state']['url']):
                raise ValueError("Closed reader evidence mismatch: body['goal'] == contract['goal'] and body['url'] == capture['state']['url']")
            observations.append(dict(capture['state'], step=i, actual_public_text=body['observation']))
            tokens += len(receipts)
        if not observations == issued['observations']:
            raise ValueError("Closed reader evidence mismatch: observations == issued['observations']")
        terminal = read(browser / 'terminal-page.json')
        receipt = read(browser / 'reader-terminal.json')
        if not (receipt['terminal'] == terminal and receipt['integrity'] is True):
            raise ValueError("Closed reader evidence mismatch: receipt['terminal'] == terminal and receipt['integrity'] is True")
        native_events = read(browser / 'reader-events.json')
        if kind == 'ny':
            if not (before == after and row['read_only_complete_baseline_preserved']):
                raise ValueError("Closed reader evidence mismatch: before == after and row['read_only_complete_baseline_preserved']")
            judgment = evaluate_ny(private, observations, terminal, origin=origin, native_unchanged=True)
        else:
            if not row['dirty_reuse_refused']:
                raise ValueError("Closed reader evidence mismatch: row['dirty_reuse_refused']")
            responses = [dict({k: v for (k, v) in response.items() if k != 'body_hex'}, body=bytes.fromhex(response['body_hex'])) for event in native_events for response in event.get('responses', [])]
            matching = [o for o in observations if o['url'] == terminal['url']]
            if not matching:
                raise ValueError('Closed reader evidence mismatch: matching')
            observed = matching[-1]
            reopened = dict(url=terminal['url'], http_status=terminal['http_status'], error=terminal['error_page'], method='GET' if any((e['event'] == 'reader_reopened' for e in native_events)) else None, visible_subscription_ids=observed['ids'], actual_public_text=observed['actual_public_text'])
            if not reopened == receipt['reopened']:
                raise ValueError("Closed reader evidence mismatch: reopened == receipt['reopened']")
            if not not any((e['event'] == 'request_error' for e in native_events)):
                raise ValueError("Closed reader evidence mismatch: not any((e['event'] == 'request_error' for e in native_events))")
            judgment = evaluate_rss(before['reader']['logical'], after['reader']['logical'], origin=origin, responses=responses, reopened=reopened)
            records = after['reader']['logical']['records']
            if not (len(records) == 1 and records[0]['url'] == origin + '/traces/rss' and (records[0]['parsed']['entries'] == 0)):
                raise ValueError("Closed reader evidence mismatch: len(records) == 1 and records[0]['url'] == origin + '/traces/rss' and (records[0]['parsed']['entries'] == 0)")
        if not judgment == receipt['judgment'] == row['judgment'] == read(folder / 'judgment.json'):
            raise ValueError("Closed reader evidence mismatch: judgment == receipt['judgment'] == row['judgment'] == read(folder / 'judgment.json')")
        if not judgment['status'] == 'success':
            raise ValueError("Closed reader evidence mismatch: judgment['status'] == 'success'")
        events = receipt['events']
        if not (events == row['lifecycle'] and events[:3] == ['prepare', 'attach', 'observe_initial']):
            raise ValueError("Closed reader evidence mismatch: events == row['lifecycle'] and events[:3] == ['prepare', 'attach', 'observe_initial']")
        if not events[-4:] == ['capture_terminal', 'close', 'provide_trace', 'score_terminal']:
            raise ValueError("Closed reader evidence mismatch: events[-4:] == ['capture_terminal', 'close', 'provide_trace', 'score_terminal']")
        if not events.count('record') == events.count('acknowledge_issued') == len(views):
            raise ValueError("Closed reader evidence mismatch: events.count('record') == events.count('acknowledge_issued') == len(views)")
        cases[kind] = dict(passed=True, source_task_id=contract['source_task_id'], judgment=judgment, actual_public_views_reconstructed=len(views), tokenizer_receipts_recounted=tokens, complete_native_state_preserved=True, ordinary_lifecycle_verified=True)
    if not origins[0] == origins[1]:
        raise ValueError('Closed reader evidence mismatch: origins[0] == origins[1]')
    warm = read(closed / 'ordinary-warm-reuse.json')
    if not warm == dict(passed=True, same_instance=True, instance_count=1, complete_baseline_unchanged=True, via_common_site_worker=True):
        raise ValueError('Closed reader evidence mismatch: warm == dict(passed=True, same_instance=True, instance_count=1, complete_baseline_unchanged=True, via_common_site_worker=True)')
    if not read(closed / 'cold-reset/full-fingerprint.json') == baseline:
        raise ValueError("Closed reader evidence mismatch: read(closed / 'cold-reset/full-fingerprint.json') == baseline")
    cold = read(closed / 'ordinary-cold-rebuild.json')
    if not cold == dict(passed=True, previous_state_removed=True, previous_reader_closed=True, new_instance_index=2, via_common_site_worker=True):
        raise ValueError('Closed reader evidence mismatch: cold == dict(passed=True, previous_state_removed=True, previous_reader_closed=True, new_instance_index=2, via_common_site_worker=True)')
    for number in (0, 1):
        folder = closed / 'site-worker' / ('map-instance-' + str(number))
        clone = read(folder / 'app-clone-progress.json')
        if not (clone['status'] == 'complete' and clone['source_modified'] is False and (clone['hardlinks_used'] is False)):
            raise ValueError("Closed reader evidence mismatch: clone['status'] == 'complete' and clone['source_modified'] is False and (clone['hardlinks_used'] is False)")
        if not (clone['completed_files'] == clone['total_files'] and clone['completed_bytes'] == clone['total_bytes']):
            raise ValueError("Closed reader evidence mismatch: clone['completed_files'] == clone['total_files'] and clone['completed_bytes'] == clone['total_bytes']")
        original = read(folder / 'existing-account-initialization.json')
        if not (original['installed_before_guard'] and original['native_model_initialization'] and (original['browser_initial_state'] == 'signed_out')):
            raise ValueError("Closed reader evidence mismatch: original['installed_before_guard'] and original['native_model_initialization'] and (original['browser_initial_state'] == 'signed_out')")
        extension = read(folder / 'local-reader-extension.json')
        if not (extension['installed_before_guard'] and extension['native_feed_interception'] is False):
            raise ValueError("Closed reader evidence mismatch: extension['installed_before_guard'] and extension['native_feed_interception'] is False")
    closure = read(closed / 'closure.json')
    if not closure == dict(passed=True, state_removed=True, ports_released=True, reader_closed=True):
        raise ValueError('Closed reader evidence mismatch: closure == dict(passed=True, state_removed=True, ports_released=True, reader_closed=True)')
    if not cases == qualified_review['cases']:
        raise ValueError("Closed reader evidence mismatch: cases == qualified_review['cases']")
    return {k: v['judgment'] for (k, v) in cases.items()}


def replay(contracts, archives, baseline, native_review, ordinary_review, reports):
    try:
        native = native_controls(contracts, archives['native'], baseline, native_review, reports['native'])
        ordinary = ordinary_controls(contracts, archives['ordinary'], baseline, ordinary_review, reports['ordinary'])
    except (AssertionError, KeyError, TypeError, IndexError) as error:
        raise ValueError('Incomplete closed reader evidence: ' + str(error)) from error
    return dict(passed=True, native_controls=native, ordinary_controls=ordinary)


def evaluate_rss(*args, **kwargs):
    """Compare current closed-control outcomes in their original RSS schema."""
    result = dict(current_evaluate_rss(*args, **kwargs))
    if result['version'] != 'native-map-rss-local-reader-v187-r2':
        raise ValueError('Explicit reviewed RSS verdict revision required')
    result['version'] = RSS_VERSION
    return result
