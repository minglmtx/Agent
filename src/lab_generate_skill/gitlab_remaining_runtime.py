"""Native callback port; source controls and scoring preserved."""
from copy import deepcopy

import hashlib

import json

from pathlib import Path

import re

from . import gitlab_remaining_components as component

from . import gitlab_remaining_native as native

from . import gitlab_remaining_state as shared

from . import gitlab_remaining_public as public

from lab_generate_skill.io_utils import atomic_write_json as write

from lab_generate_skill.source_revision_binding import binding

from lab_generate_skill.gitlab_native_read_runtime import full_snapshot

from lab_generate_skill.gitlab_persisted_goal_runtime import refs_snapshot, validate_refs

from lab_generate_skill.gitlab_native_csv_probe import (auth_backup, restore_auth_metadata,
    protected_snapshot_session, queue_snapshot, existing_jobs_preserved, normalize_reference)

from lab_generate_skill.gitlab_project_creation import project_state

from lab_generate_skill.gitlab_mutation_native import repository

from lab_generate_skill.site_navigation_rules import valid_initial_page

VERSION = 'gitlab-remaining-ordinary-cpu-v1'

def read(path): return json.loads(Path(path).read_text())

def artifact(directory, name):
    directory = Path(directory).resolve(); path = directory / name
    if not path.is_file() or path.is_symlink() or directory not in path.resolve().parents:
        raise ValueError('Exact original private artifact required: ' + name)
    return path

def expectations(c):
    names = {'initial_no_op': 'failure', 'positive': 'success', 'wrong_object': 'failure',
        '404': 'failure', 'login': 'failure'}
    if c['family'] == 'native_repository_template': names.update(unsaved='failure', wrong_template='failure')
    if c['family'] == 'native_all_merge_request_csv': names.update(queued_without_attachment='failure', wrong_open_filter='failure')
    return names

class CsvTransport(component.csv_runtime.NativeCsvHooks):
    """Same native transport, explicit first-control bootstrap, no fake proof."""
    def __init__(self, c, private, directory):
        super().__init__(c, {}, directory); self.private = deepcopy(private)
        self.queue_final = None
    def prepare(self, site, username, *, parent=None):
        if self.prepared: raise ValueError('One actual native CSV prepare required')
        from lab_generate_skill.gitlab_native_csv_probe import private_json
        self.site = site; self.username = username
        if parent is None:
            self.native_initial = protected_snapshot_session(site, self.directory / 'csv-protected-progress.jsonl')
        else:
            self.native_initial = component.csv_runtime.prepared_parent_snapshot(parent, self, site)
            write(self.directory / 'csv-shared-preparation.json',
                {'version': 'same-control-fresh-csv-preparation-v1',
                 'generation': site.generation, 'fresh_common_capture_consumed_once': True,
                 'prior_control_or_saved_snapshot_reused': False})
        full_snapshot(self.native_initial); self.account = auth_backup(site, username)
        if self.account['id'] != self.private['account_id']: raise ValueError('Actual current native CSV account differs')
        cfg = (site.state / 'data/gitlab-rails/etc/gitlab.yml').read_text()
        if not re.search(r'^\s*email_enabled:\s*false\s*$', cfg, re.M): raise component.PendingCapability('Local bounded CSV transport requires external email disabled')
        reference = native.native_csv_reference(site, self.private['project']['id'], self.account['id'], self.directory / 'prepare-csv-reference')
        if reference != self.private['reference']: raise ValueError('Fresh actual complete All reference changed')
        self.gate = {'version': component.csv_admission.VERSION, 'private_reference': reference,
            'source_task_id': self.contract['source_task_id'], 'native_state': 'all'}
        self.chain = native.capture_csv_chain(site)
        self.gate['native_chain'] = self.chain
        write(self.directory / 'csv-installed-chain.json', self.chain)
        self.queue_initial = queue_snapshot(site, self.directory / 'csv-queue-progress.jsonl')
        private_json(self.directory / 'csv-native-before.json', self.native_initial)
        private_json(self.directory / 'csv-queues-before.json', self.queue_initial)
        self.prepared = True
    def after_action(self, page):
        if self.activations or self.responses:
            # Preserve the actual complete vectors before the installed
            # transport atomically claims its observed JID. The installed
            # privacy-safe discovery alone does not contain original vectors.
            write(self.directory / ('csv-actual-queue-' + str(len(self.claimed)) + '.json'),
                {'before': self.before_action_queues,
                 'after': queue_snapshot(self.site, self.directory / 'csv-queue-progress.jsonl')})
        return super().after_action(page)
    def score_terminal(self, terminal, *, runtime_error=False):
        j, integrity = super().score_terminal(terminal, runtime_error=runtime_error)
        self.queue_final = queue_snapshot(self.site, self.directory / 'csv-queue-progress.jsonl')
        write(self.directory / 'csv-queues-after.json', self.queue_final)
        write(self.directory / 'csv-original-native-receipts.json', self.received)
        return j, integrity

class Hooks(shared.Hooks):
    def __init__(self, c, private, directory, *, proof=None, proof_session=None):
        self.contract, self.private, self.directory = deepcopy(c), deepcopy(private), Path(directory)
        if proof is None: raise ValueError("Complete source-bound native admission proof required")
        else:
            if proof_session is None:
                first = require_proof(c, proof)
            else:
                from lab_generate_skill.native_proof_session import NativeProofSession
                if not isinstance(proof_session, NativeProofSession):
                    raise ValueError('A live native proof session is required')
                verified = proof_session.reuse_verified(c, proof)
                first = (verified['gate_return']['first_control'] if 'groups' in verified
                         else verified['cycles'][0]['controls']['initial_no_op'])
            if private != first['private_reference']: raise ValueError('Normal native reference differs from both cold groups')
        self.expected_baseline = None if proof is None else (first['native_before_initialization'], first['protected_before'], first['refs_before'])
        self.context = self.site = self.initial_page = None
        self.events = []; self.scored = False; self.prepared = False; self.issued = []
        self.csv = None; self.negative_block_consumer = False
        self.template_worker = None

        self.terminal = None; self.current_page = None; self.closed = False
    def prepare(self, site, username):
        self.auth_username = username
        if self.contract['family'] == 'native_monitoring_section':
            from lab_generate_skill.gitlab_metrics_fixture import require_prepared
            require_prepared(site, self.contract, username)
        self.prepare_generation = site.generation
        super().prepare(site, username)
        if self.prepare_generation != site.generation:
            raise ValueError('Reset crossed common native preparation')
        if self.contract['family'] == 'native_repository_template':
            self.template_before = native.capture_full_rows(site, self.directory / 'template-before-progress.jsonl')
            if self.template_before['full'] != self.before: raise ValueError('Full native template baseline changed')
            if native.template_baseline(site, username) != self.private['baseline']: raise ValueError('Fresh native template account/project baseline differs')
            write(self.directory / 'template-full-rows-before.json', self.template_before)
            self.template_queues = queue_snapshot(site, self.directory / 'template-queue-progress.jsonl')
            write(self.directory / 'template-queues-before.json', self.template_queues)
        elif self.contract['family'] == 'native_all_merge_request_csv':
            self.csv = CsvTransport(self.contract, self.private, self.directory)
            self.csv.prepare(site, username, parent=self)
            if self.csv.native_initial != self.before: raise ValueError('Full CSV and common native baseline differ')
    def acknowledge_issued(self, ax):
        if not isinstance(ax, str) or not ax.strip() or self.initial_page is None: raise ValueError('Actual issued nonempty AX required')
        self.issued.append(hashlib.sha256(ax.encode()).hexdigest())
        write(self.directory / 'issued-ax-receipts.json', self.issued)
    def record(self, page):
        super().record(page)
        if self.contract['family'] == 'native_repository_template' and self.template_worker is None:
            final = project_state(self.site, self.auth_username)
            old = {p['id'] for p in self.private['baseline']['project_state']['projects']}
            new = [p for p in final['projects'] if p['id'] not in old]
            if new:
                # Real ordinary creation only. A blank-project negative does
                # not have an import job and must not be converted to a template.
                jobs = queue_snapshot(self.site, self.directory / 'template-queue-progress.jsonl')
                if any(j['job'].get('class') == 'RepositoryImportWorker' and j['job'].get('args') == [new[0]['id']] for j in jobs):
                    self.template_worker = native.consume_template_import(self.site, self.contract,
                        self.private, self.template_queues, self.directory)
    def capture_terminal(self, page, terminal):
        page_lifetime.terminal_page(self, page, terminal)
        family = self.contract['family']
        if family == 'native_group_hierarchy': terminal['native_hierarchy'] = component.capture_hierarchy(page)
        elif family == 'native_monitoring_section': terminal['gitlab_grouped_goal'] = component.grouped.read_native(page, 'project_section')
        self.terminal = terminal; self.events.append('capture_terminal')
    def score_terminal(self, site, terminal, *, runtime_error=None):
        score_complete = page_lifetime.score_bound(self, site, terminal, runtime_error)
        self.scored = True; self.events.append('score_terminal'); family = self.contract['family']
        restore_auth_metadata(site, self.auth)
        # CSV's native consumer obtains the authoritative complete after-state.
        # Do not scan again before that consumer, then discard the duplicate.
        after = refs_after = None
        if family != 'native_all_merge_request_csv':
            after = protected_snapshot_session(site, self.directory / 'full16-after-progress.jsonl'); full_snapshot(after)
            refs_after = refs_snapshot(site)
        reference_after = deepcopy(self.private)
        final = effects = rows_after = repository_after = csv_integrity = None
        if family == 'native_group_hierarchy':
            reference_after = component.hierarchy_reference(site, self.contract['public_parameters'].get('username', self.auth_username))
            result = component.hierarchy_terminal(self.contract, terminal, self.private, site_origin=site.url,
                full_before=self.before, full_after=after, refs_before=self.refs_before, refs_after=refs_after,
                reference_after=reference_after, runtime_error=runtime_error) if score_complete else None
            integrity = self.before == after and self.refs_before == refs_after and reference_after == self.private
        elif family == 'native_monitoring_section':
            reference_after = component.metrics_reference(site, self.contract)
            integrity = self.before == after and self.refs_before == refs_after and reference_after == self.private
            result = component.metrics_checks(self.contract, terminal, self.private, site_origin=site.url, runtime_error=runtime_error) if score_complete else None
        elif family == 'native_repository_template':
            final = project_state(site, self.auth_username)
            effects = native.authorized_creation(site, self.contract, self.private['baseline'], final)
            rows_after = native.capture_full_rows(site, self.directory / 'template-after-progress.jsonl')
            if rows_after['full'] != after: raise ValueError('Native complete template after capture changed')
            write(self.directory / 'template-full-rows-after.json', rows_after)
            integrity = native.creation_guard(self.template_before, rows_after, effects) and native.creation_refs_guard(self.refs_before, refs_after, effects)
            p = effects['created_project']; repository_after = None
            if p:
                try: repository_after = repository(site, p['id'], '')
                except Exception: repository_after = {'identity': p['id'], 'head': None, 'branch': None, 'refs': {}, 'files': {}}
            checks = component.template_content_checks(self.contract, self.private['baseline']['project_state'], final,
                self.private['template'], repository_after or {})
            checks['valid_terminal_page'] = valid_initial_page(terminal, site_origin=site.url) if score_complete else False
            result = judgment(checks)
        else:
            if self.negative_block_consumer:
                if not self.csv.pending or self.csv.received: raise ValueError('Real queued-but-not-delivered negative required')
                self.csv.consumed = True
            result, csv_integrity = self.csv.score_terminal(terminal, runtime_error=not score_complete)
            after = read(self.directory / 'csv-native-after.json'); full_snapshot(after)
            refs_after = refs_snapshot(site)  # after native CSV delivery, not before
            integrity = (self.before == after and self.refs_before == refs_after and
                all(csv_integrity[k] for k in ('native_full_state_preserved', 'native_prior_queues_preserved', 'bound_auth_metadata_restored')))
        if not score_complete or not integrity: result = {'status': 'unknown', 'reward': None, 'checks': {}, 'reason': 'Actual runtime or complete native protection incomplete'}
        self.receipt = {'version': VERSION, 'original_binding': binding(self.contract), 'contract': self.contract,
            'private_reference': self.private, 'reference_after': reference_after, 'site_origin': site.url,
            'events': self.events, 'issued_ax_sha256': self.issued, 'terminal': terminal, 'judgment': result,
            'native_before_initialization': self.cold, 'native_initialization_effects': self.effects,
            'protected_before': self.before, 'protected_after': after, 'refs_before': self.refs_before, 'refs_after': refs_after,
            'template_full_before': getattr(self, 'template_before', None), 'template_full_after': rows_after,
            'template_effects': effects, 'template_final': final, 'template_repository': repository_after,
            'template_native_worker': self.template_worker,
            'csv_integrity': csv_integrity, 'csv_claimed_jobs': self.csv.claimed if self.csv else None,
            'csv_pending': self.csv.pending if self.csv else None,
            'csv_faults': self.csv.faults if self.csv else None,
            'auth_metadata_restored': auth_backup(site, self.auth_username) == self.auth,
            'negative_control_block_consumer': self.negative_block_consumer,
            'actor_attempts': 0, 'api_calls': 0, 'formal_training_admission': False, 'integrity': integrity}
        write(self.directory / 'native-private-receipt.json', self.receipt)
        return result, integrity
    def prepare_account(self, site, username):
        self.auth_username = username; self.prepare(site, username)

def judgment(checks):
    passed = all(checks.values())
    return {'status': 'success' if passed else 'failure', 'reward': float(passed), 'checks': checks, 'reason': None}

def make_hooks(c, private, directory, *, proof):
    """Ordinary inference constructor; actual two-cold source proof is mandatory."""
    return Hooks(c, private, directory, proof=proof)

CSV_ARTIFACT_NEGATIVES = ('wrong_user_reference', 'wrong_collection_receipt', 'truncated_receipt',
    'missing_column', 'missing_row', 'altered_field')

def csv_artifact_negatives(received, reference, origin):
    """Replay typed mutations of actual complete MIME data, retain each input."""
    if not received or not received.get('rows'): raise ValueError('Actual populated MIME receipt required')
    gate = {'version': component.csv_admission.VERSION, 'private_reference': reference}
    values = {}
    for name in CSV_ARTIFACT_NEGATIVES:
        item, ref = deepcopy(received), deepcopy(reference)
        if name == 'wrong_user_reference': ref['user_id'] += 1
        elif name == 'wrong_collection_receipt': item['native_context']['type'] = 'issue'
        elif name == 'truncated_receipt': item['native_context']['truncated'] = True
        elif name == 'missing_column':
            key = item['headers'].pop()
            for row in item['rows']: row.pop(key)
        elif name == 'missing_row': item['rows'] = item['rows'][1:]
        elif name == 'altered_field': item['rows'][0]['Title'] += ' [wrong]'
        actual_gate = dict(gate, private_reference=ref)
        result = component.csv_admission.score_received(actual_gate, item, site_origin=origin)
        values[name] = {'received': item, 'reference': ref, 'judgment': result,
            'artifact_consistency_negative_not_another_account_ui': True}
    return values

def _csv_inputs(folder, row):
    """Bind actual activation/JID discovery, complete native chain and MIME."""
    from probe_gitlab_native_csv_controls import read_delivery, consumer_ruby
    from lab_generate_skill.gitlab_native_csv_probe import new_export_job
    folder = Path(folder); chain = read(artifact(folder, 'csv-installed-chain.json'))
    if set(chain) != component.csv_admission.CHAIN_FILES or any(not re.fullmatch('[0-9a-f]{64}', x) for x in chain.values()):
        raise ValueError('Exact complete installed native export chain required')
    before = read(artifact(folder, 'csv-queues-before.json')); after = read(artifact(folder, 'csv-queues-after.json'))
    if not existing_jobs_preserved(before, after, row['csv_claimed_jobs']):
        raise ValueError('Every original native job must be preserved')
    pending = row['csv_pending']
    if row['csv_faults'] or [v['job']['jid'] for v in pending] != row['csv_claimed_jobs']:
        raise ValueError('Exact native pending jobs/claims without transport faults required')
    for i, v in enumerate(pending):
        observed = v['observed']; discovery = read(artifact(folder, 'csv-actual-queue-' + str(i) + '.json'))
        # Discovery includes complete namespaced vectors; recompute the sole
        # newly requested unchanged native job, not a supplied queued boolean.
        actual = new_export_job(discovery['before'], discovery['after'], kind=observed['kind'],
            user_id=row['private_reference']['account_id'], project_id=observed['project_id'], state=observed['state'])
        from lab_generate_skill.gitlab_native_csv_probe import native_export_discovery_capture
        if native_export_discovery_capture(discovery['before'], discovery['after']) != read(artifact(folder, 'csv-discovery-' + str(i) + '.json')):
            raise ValueError('Installed native discovery differs from original complete actual vectors')
        if actual['job'] != v['job']: raise ValueError('Actual native JID discovery differs')
        claim = read(artifact(folder, 'csv-claimed-' + f'{i+1:02d}' + '.json'))
        if claim['job_id'] != v['job']['jid'] or claim['observed'] != observed or claim['raw_sha256'] != v['claim']['raw_sha256']:
            raise ValueError('Original trusted native activation/request/JID claim differs')
    original = read(artifact(folder, 'csv-original-native-receipts.json'))
    if row['negative_control_block_consumer']:
        if not pending or original or (folder / 'csv-consumer-terminal').exists():
            raise ValueError('Queued-without-attachment must retain real native job and no MIME')
    elif pending:
        saved = folder / 'csv-consumer-terminal' / 'native-delivery'
        process = read(artifact(folder / 'csv-consumer-terminal', 'consumer-process.json'))
        if process['returncode'] != 0 or process['failure'] is not None or process['rails_global_new_help_detected']:
            raise ValueError('Actual native application worker must complete within budget')
        if artifact(saved, 'consumer.rb').read_text() != consumer_ruby(): raise ValueError('Actual pinned native MIME consumer differs')
        raw_jobs = read(artifact(saved, 'native-jobs.json'))
        if raw_jobs != [{'job': p['job'], 'claim': p['claim']} for p in pending]: raise ValueError('Actual native worker consumed another JID bundle')
        installed = read(artifact(saved, 'installed-native-chain.json'))
        if installed['source_sha256'] != chain: raise ValueError('Worker actual native source chain differs')
        results = read(artifact(saved, 'native-consumer-result.json'))
        if len(results) != len(pending) or any(r.get('stage') != 'complete' or r.get('reference_unchanged') is not True for r in results):
            raise ValueError('Actual unchanged complete native references/worker results required')
        parsed = [read_delivery(saved, v['job']['jid']) for v in pending]
        if parsed != original: raise ValueError('Reparsed actual full MIME does not match complete original receipt')
        for v in pending:
            ref0 = read(artifact(saved, v['job']['jid'] + '-reference-before.json'))
            ref1 = read(artifact(saved, v['job']['jid'] + '-reference-after.json'))
            if ref0 != ref1: raise ValueError('Actual independent native reference changed during export')
            if v['observed']['project_id'] == row['private_reference']['project']['id'] and v['observed']['state'] == 'all':
                if normalize_reference(ref0, row['site_origin']) != row['private_reference']['reference']:
                    raise ValueError('Complete actual native All reference differs from private source reference')
    elif original: raise ValueError('No native request may invent a MIME receipt')
    integrity = (row['protected_before'] == row['protected_after'] and
        row['refs_before'] == row['refs_after'] and row['auth_metadata_restored'] is True)
    healthy = valid_initial_page(row['terminal'], site_origin=row['site_origin'])
    gate = {'version': component.csv_admission.VERSION, 'private_reference': row['private_reference']['reference']}
    judgments = [component.csv_admission.score_received(gate, item, site_origin=row['site_origin'],
        page_valid=healthy, complete_state_preserved=integrity,
        complete_prior_queue_preserved=True) for item in original or [None]]
    result = next((j for j in reversed(judgments) if j['status'] == 'success'), judgments[-1])
    return result, integrity, chain

def require_control(c, row, expected, folder):
    component.enabled(c); public.public_input(c); folder = Path(folder)
    if (row['version'] != VERSION or row['original_binding'] != binding(c) or row['contract'] != c
        or row['actor_attempts'] != 0 or row['api_calls'] != 0 or row['formal_training_admission'] is not False
        or read(artifact(folder, 'native-private-receipt.json')) != row):
        raise ValueError('Exact original zero-model source/private control receipt required')
    shared.verify_initialization(folder, row)
    for k in ('native_before_initialization', 'protected_before', 'protected_after'): full_snapshot(row[k])
    validate_refs(row['refs_before']); validate_refs(row['refs_after'])
    first = read(artifact(folder, 'step-000.json'))['observation']
    if first.get('goal') != public.render(c) or not first.get('axtree_txt'):
        raise ValueError('Actual ordinary initial public task and AX required')
    issued = read(artifact(folder, 'issued-ax-receipts.json'))
    if not issued or issued != row['issued_ax_sha256'] or issued[0] != hashlib.sha256(first['axtree_txt'].encode()).hexdigest():
        raise ValueError('Actual nonempty issued AX acknowledgement required')
    events = row['events']
    if events[:3] != ['prepare', 'attach', 'observe_initial'] or 'record' not in events or events[-2:] != ['capture_terminal', 'score_terminal']:
        raise ValueError('Complete ordinary factory lifecycle required')
    if read(artifact(folder, 'terminal-page.json')) != row['terminal']:
        raise ValueError('Original actual terminal page differs')
    private = read(artifact(folder.parent, 'private-reference.json'))
    if private != row['private_reference']: raise ValueError('All controls must bind one complete native source reference')
    family = c['family']; extra = None
    if family == 'native_group_hierarchy':
        integrity = row['protected_before'] == row['protected_after'] and row['refs_before'] == row['refs_after'] and private == row['reference_after']
        result = component.hierarchy_terminal(c, row['terminal'], private, site_origin=row['site_origin'],
            full_before=row['protected_before'], full_after=row['protected_after'], refs_before=row['refs_before'],
            refs_after=row['refs_after'], reference_after=row['reference_after'])
    elif family == 'native_monitoring_section':
        integrity = row['protected_before'] == row['protected_after'] and row['refs_before'] == row['refs_after'] and private == row['reference_after']
        result = component.metrics_checks(c, row['terminal'], private, site_origin=row['site_origin'])
    elif family == 'native_repository_template':
        entry = private['template']
        component.qualify_local_template([entry], {'files': entry['repository_files']}, template_name=c['public_parameters']['template_name'])
        raw = read(artifact(folder.parent / 'template-native-reference', 'native-reference.json'))
        invoke = read(artifact(folder.parent / 'template-native-reference', 'native-invocation.json'))
        if raw['qualified'] != entry or raw['catalogue'] != private['native_catalogue'] or invoke['returncode'] != 0 or invoke['script_sha256'] != hashlib.sha256(Path(native.__file__).with_name('native_template_reference.rb').read_bytes()).hexdigest():
            raise ValueError('Actual pinned independent local template invocation differs')
        if (read(artifact(folder, 'template-full-rows-before.json')) != row['template_full_before']
            or read(artifact(folder, 'template-full-rows-after.json')) != row['template_full_after']
            or row['template_full_before']['full'] != row['protected_before']
            or row['template_full_after']['full'] != row['protected_after']):
            raise ValueError('Complete native template raw row fingerprints differ')
        native.verify_creation_effects(c, private['baseline'], row['template_final'], row['template_effects'])
        worker = row['template_native_worker']
        if worker is not None:
            if read(artifact(folder, 'template-native-worker-receipt.json')) != worker:
                raise ValueError('Actual bounded local template native worker receipt differs')
            queues = read(artifact(folder, 'template-queues-before.json'))
            if queues != worker['before']: raise ValueError('Original pre-UI template queue baseline differs')
            p = row['template_effects']['created_project']; account = private['baseline']['project_state']['user']['id']
            if p is None or native.template_job(queues, worker['after_request'], p['id']) != worker['record']:
                raise ValueError('Actual new local template import job differs')
            if not existing_jobs_preserved(queues, worker['after_worker'], [worker['record']['job']['jid']]):
                raise ValueError('Prior native queues lost during local template import')
            raw_worker = read(artifact(folder / 'template-native-worker', 'native-reference.json'))
            invoked = read(artifact(folder / 'template-native-worker', 'native-invocation.json'))
            if (raw_worker != worker['native_worker'] or invoked['returncode'] != 0
                or invoked['script_sha256'] != hashlib.sha256(Path(native.__file__).with_name('native_template_worker.rb').read_bytes()).hexdigest()
                or raw_worker['actual_ui_job_id'] != worker['record']['job']['jid'] or raw_worker['actual_native_arguments'] != [p['id']]
                or raw_worker['project_id'] != p['id'] or raw_worker['account_id'] != account
                or raw_worker['full_path'] != p['full_path'] or raw_worker['import_status'] != 'finished'
                or raw_worker['local_gitlab_project_import'] is not True or raw_worker['remote_import_url_present'] is not False
                or raw_worker['native_project_created_by_bridge'] is not False):
                raise ValueError('Actual pinned successful local native import worker invocation differs')
            expected_chain = {'app/workers/repository_import_worker.rb', 'app/services/projects/import_service.rb',
                'app/services/projects/create_from_template_service.rb', 'app/services/projects/gitlab_projects_import_service.rb',
                'lib/gitlab/project_template.rb'}
            if set(raw_worker['native_source_sha256']) != expected_chain or any(not re.fullmatch('[0-9a-f]{64}', v) for v in raw_worker['native_source_sha256'].values()):
                raise ValueError('Complete native local import source fingerprints required')
            extra = raw_worker['native_source_sha256']
        integrity = native.creation_guard(row['template_full_before'], row['template_full_after'], row['template_effects']) and native.creation_refs_guard(row['refs_before'], row['refs_after'], row['template_effects'])
        checks = component.template_content_checks(c, private['baseline']['project_state'], row['template_final'], entry, row['template_repository'] or {})
        checks['valid_terminal_page'] = valid_initial_page(row['terminal'], site_origin=row['site_origin'])
        result = judgment(checks)
    else: result, integrity, extra = _csv_inputs(folder, row)
    recorded_matches = result == row['judgment']
    if family == 'native_monitoring_section' and not recorded_matches:
        # Original raw files, initialization, full protection, task identity and
        # current terminal were checked above. Only the documented controller
        # name mismatch may be reclassified; original records stay untouched.
        from lab_generate_skill.gitlab_metrics_rejudgment import recorded_verdict_matches
        recorded_matches = recorded_verdict_matches(row['judgment'], result, row['terminal'])
    if row['auth_metadata_restored'] is not True or not integrity or row['integrity'] is not True or not recorded_matches or result['status'] != expected:
        raise ValueError('Recomputed original native protection and terminal verdict did not pass')
    return extra

def _reset(row):
    if (row.get('generation_after') != row.get('generation_before', -2) + 1
        or row.get('event', {}).get('phase') != 'reset_total'
        or row['event'].get('restore', {}).get('restore_complete') is not True):
        raise ValueError('Actual complete native reset event required')

def _materialization_matches(source, materialized):
    if source.get('gitlab_cache_initialization') != materialized.get('gitlab_cache_initialization'):
        raise ValueError('Native cache profile changed after source selection')
    if binding(source) != binding(materialized) or source['family'] != materialized['family']:
        raise ValueError('Exact original source/goal/all starts/traces/family required')
    component.enabled(materialized); public.public_input(materialized)
    for key, value in source['public_parameters'].items():
        if value is not None and materialized['public_parameters'].get(key) != value:
            raise ValueError('Declared public parameter changed after source selection: ' + key)
    return True

def require_two_cold(case, cycles, folders):
    """Fail closed; recompute complete original records from both cold workers."""
    if not isinstance(cycles, list) or len(cycles) != 2 or len(folders) != 2:
        raise ValueError('Two complete independent original cold result directories required')
    ids = [x.get('fresh_instance_id') for x in cycles]
    if any(not re.fullmatch('[0-9a-f]{64}', x or '') for x in ids) or ids[0] == ids[1]:
        raise ValueError('Distinct actual native cold state identities required')
    references = []; baselines = []; contracts = []; chains = []
    for cycle, directory in zip(cycles, folders):
        directory = Path(directory)
        if (read(artifact(directory, 'cycle.json')) != cycle or cycle['version'] != VERSION
            or cycle['source_task_id'] != case['source_task_id'] or cycle['actor_attempts'] != 0
            or cycle['api_calls'] != 0 or cycle['training_admitted'] is not False or cycle['normal_gate_passed'] is not False):
            raise ValueError('Exact original first-control source cycle required')
        c = cycle['contract']; _materialization_matches(case, c)
        if read(artifact(directory, 'materialized-contract.json')) != c: raise ValueError('Actual complete public materialization differs')
        expected = expectations(c)
        if set(cycle['controls']) != set(expected) or set(cycle['reset_controls']) != set(expected):
            raise ValueError('All actual ordinary positive/negative/reset controls required')
        local = []
        for name, status in expected.items():
            extra = require_control(c, cycle['controls'][name], status, directory / name)
            if extra is not None: chains.append(extra)
            _reset(cycle['reset_controls'][name])
            r = cycle['controls'][name]
            local.append((r['native_before_initialization'], r['protected_before'], r['refs_before']))
        if any(v != local[0] for v in local): raise ValueError('Every complete reset baseline must be equal')
        final = read(artifact(directory, 'final-reset.json')); _reset(final)
        if final != cycle['final_reset'] or (final['cold'], final['before'], final['refs']) != local[0]:
            raise ValueError('Actual complete final source reset did not reproduce all native state')
        shared.verify_initialization(directory / 'final-reset', {'native_initialization_effects': final['effects'],
            'native_before_initialization': final['cold'], 'protected_before': final['before']})
        private = cycle['controls']['initial_no_op']['private_reference']
        baseline = (private['baseline'] if c['family'] == 'native_repository_template' else
            private['reference'] if c['family'] == 'native_all_merge_request_csv' else private)
        if final['private_baseline'] != baseline: raise ValueError('Actual independent private baseline not restored')
        if c['family'] == 'native_all_merge_request_csv':
            received = read(artifact(directory / 'positive', 'csv-original-native-receipts.json'))
            actual = csv_artifact_negatives(received[0], private['reference'], cycle['controls']['positive']['site_origin'])
            if read(artifact(directory, 'csv-artifact-negatives.json')) != actual or actual != cycle['csv_artifact_negatives'] or any(v['judgment']['status'] != 'failure' for v in actual.values()):
                raise ValueError('Complete typed negative MIME/reference inputs and recalculated failure required')
        elif cycle['csv_artifact_negatives']: raise ValueError('Unrelated family cannot manufacture CSV artifact proof')
        cleanup = read(artifact(directory.parent, 'worker-cleanup.json'))
        state_path = cleanup.get('native_site_state_path', cleanup.get('original_state_path'))
        if (not isinstance(state_path, str) or not Path(state_path).is_absolute()
            or hashlib.sha256(state_path.encode()).hexdigest() != cycle['fresh_instance_id']
            or cleanup.get('fresh_instance_id') != cycle['fresh_instance_id']
            or cleanup.get('state_exists_after_close') is not False or cleanup.get('services_stopped') is not True
            or cleanup.get('remaining_process_ids') != [] or cleanup.get('native_site_exit_completed') is not True):
            raise ValueError('Actual independent native worker exit/owned cleanup required')
        contracts.append(c); references.append(private); baselines.append(local[0])
    if contracts[0] != contracts[1] or references[0] != references[1] or baselines[0] != baselines[1] or any(v != chains[0] for v in chains):
        raise ValueError('Actual independent cold public/reference/full16/root-ref/source-chain records disagree')
    return {'version': VERSION, 'passed': True, 'source_task_id': case['source_task_id'],
        'contract': deepcopy(contracts[0]), 'fresh_instance_ids': ids, 'fresh_cycles': 2,
        'ordinary_controls_per_cold': len(expectations(contracts[0])),
        'actor_attempts': 0, 'api_calls': 0, 'training_admission_written': False}

from . import native_artifact_page_lifetime as page_lifetime

def require_proof(c, proof):
    """Use complete cold cycles or explicit original-controls/reset supplements."""
    if proof.get('version') == 'native-csv-retained-controls-reset-supplement-v1':
        return require_supplement(c, proof['groups'])['first_control']
    require_two_cold(c, proof['cycles'], proof['directories'])
    return proof['cycles'][0]['controls']['initial_no_op']

def require_supplement(c, groups):
    import sys
    from lab_generate_skill.native_csv_supplement_admission import require_supplement as verify
    return verify(sys.modules[__name__], c, groups)
