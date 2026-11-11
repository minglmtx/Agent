"""Optional terminal-only lifecycle for independently controlled native reads.

This does not navigate, correct actions, inject reference text, or infer task
completion during a rollout. Private source/help bytes and full database
fingerprints stay in evaluator artifacts. Actual CPU evidence is required;
these hooks alone never constitute an admission.
"""
from copy import deepcopy
from pathlib import Path
import re
from urllib.parse import urlsplit

from .gitlab_native_csv_probe import (PROTECTED_TABLES, protected_snapshot_session as protected_snapshot,
                                    auth_backup, restore_auth_metadata)
from .io_utils import atomic_write_json
from .navigation_click_evidence import NavigationClicks

VERSION = 'gitlab-native-read-runtime-v1'
PROOF_VERSION = 'gitlab-native-read-runtime-controls-v1'
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
SHA = re.compile(r'[0-9a-f]{64}')
PRIVATE_SCOPE = 'local_native_document_retrieval'


def primitive():
    # These independently tested native readers are archived with the runtime;
    # the scripts directory is part of the ordinary runner's import path.
    import gitlab_native_read_completion
    return gitlab_native_read_completion


def full_snapshot(value):
    if not isinstance(value, dict) or set(value) != set(PROTECTED_TABLES):
        raise ValueError('All sixteen native protected tables required')
    for table, state in value.items():
        if (not isinstance(state, dict) or set(state) != {'rows', 'columns', 'key', 'sha256'}
                or type(state['rows']) is not int or state['rows'] < 0
                or not isinstance(state['columns'], list) or not state['columns']
                or not isinstance(state['key'], list) or not state['key']
                or any(not isinstance(x, str) or not NAME.fullmatch(x)
                       for x in state['columns'] + state['key'])
                or len(set(state['columns'])) != len(state['columns'])
                or len(set(state['key'])) != len(state['key'])
                or not set(state['key']) <= set(state['columns'])
                or not isinstance(state['sha256'], str) or not SHA.fullmatch(state['sha256'])):
            raise ValueError('Complete native protected schema/row/key digest required: ' + table)
    return value


def enabled(contract):
    if 'gitlab_native_read' not in contract:
        return False
    spec = contract['gitlab_native_read']
    if (contract.get('domain') != 'gitlab' or not isinstance(spec, dict)
            or spec.get('version') != VERSION or spec.get('scope') != PRIVATE_SCOPE
            or contract.get('eligible_for_training') is not False
            or contract.get('heldout_quarantine') is not False
            or contract.get('not_original_benchmark_equivalence') is not True):
        raise ValueError('Explicit development native document protocol required')
    other = ('native_csv_export', 'query', 'fork_creation', 'project_creation',
             'ref_creation', 'clipboard', 'repository_download', 'membership',
             'preferences', 'cart', 'vote', 'catalog', 'search', 'wiki', 'todo',
             'issue_creation', 'group_creation', 'reviewed_reddit_family', 'map_export')
    if any(contract.get(k) for k in other) or contract.get('completion'):
        raise ValueError('Native read cannot mix another completion family')
    if (not isinstance(contract.get('source_task_id'), str)
            or not isinstance(contract.get('goal'), str) or not contract['goal']
            or not isinstance(contract.get('recorded_start_paths'), list)
            or not contract['recorded_start_paths']
            or contract.get('start_path') != contract['recorded_start_paths'][0]
            or not isinstance(contract.get('source_trace_ids'), list)
            or not contract['source_trace_ids']):
        raise ValueError('Original source, goal, first start and all traces required')
    return True


def evaluate_any(references, captures, *, site_origin):
    if not isinstance(captures, list) or len(captures) != len(references) or not references:
        return {'status': 'unknown', 'reward': None, 'checks': {},
                'reason': 'Complete native terminal capture required'}
    judgments = [primitive().evaluate(spec, state, site_origin=site_origin)
                 for spec, state in zip(references, captures)]
    status = ('success' if any(x['status'] == 'success' for x in judgments) else
              'unknown' if any(x['status'] == 'unknown' for x in judgments) else 'failure')
    chosen = next((x for x in judgments if x['status'] == status), judgments[0])
    # Alternative documents are permitted by the declared reference set; all
    # individual judgments remain private for diagnosis.
    return {'version': VERSION, 'status': status,
            'reward': None if status == 'unknown' else float(status == 'success'),
            'checks': deepcopy(chosen['checks']), 'private_alternatives': judgments}


def require_original_binding(contract, original, inventory):
    enabled(contract)
    if {k: v for k, v in contract.items() if k != 'admission_result'} != original:
        raise ValueError('Native read runtime binding changed after controls')
    def path(value):
        parsed = urlsplit(value)
        return (parsed.path or '/') + ('?' + parsed.query if parsed.query else '') + (
                '#' + parsed.fragment if parsed.fragment else '')
    if (not isinstance(inventory, dict) or inventory.get('domain') != 'gitlab'
            or inventory.get('task_id') != contract.get('source_task_id')
            or inventory.get('heldout_quarantine') is not False
            or inventory.get('goal') != contract.get('original_goal', contract['goal'])
            or inventory.get('source_trace_ids') != contract['source_trace_ids']
            or [path(x) for x in inventory.get('recorded_start_urls', [])]
               != contract['recorded_start_paths']):
        raise ValueError('Authoritative original native goal/start/trace binding differs')


def require_admission(contract, proof):
    if not enabled(contract) or not isinstance(proof, dict) or proof.get('version') != PROOF_VERSION:
        raise ValueError('Versioned native read runtime controls required')
    identity = {k: contract[k] for k in ('source_task_id', 'goal', 'start_path',
                                       'recorded_start_paths', 'source_trace_ids')}
    if proof.get('original_binding') != identity or proof.get('scope') != PRIVATE_SCOPE:
        raise ValueError('Original native source/goal/start/trace scope differs')
    if (proof.get('actor_attempts') != 0 or type(proof.get('actor_attempts')) is not int
            or proof.get('api_calls') != 0 or type(proof.get('api_calls')) is not int
            or proof.get('formal_preinference_lifecycle_verified') is not True):
        raise ValueError('Actual zero-model formal lifecycle validation required')
    cycles = proof.get('cycles')
    if not isinstance(cycles, list) or len(cycles) != 2 or any(not isinstance(c, dict) for c in cycles):
        raise ValueError('Two independent native reset cycles required')
    ids = [c.get('fresh_instance_id') for c in cycles]
    if any(not isinstance(x, str) or not SHA.fullmatch(x) for x in ids) or len(set(ids)) != 2:
        raise ValueError('Two distinct native instance identities required')
    for cycle in cycles:
        for name in ('native_before_initialization', 'protected_before', 'protected_after'):
            full_snapshot(cycle.get(name))
        if cycle['protected_before'] != cycle['protected_after']:
            raise ValueError('Complete post-initialization native protection changed')
        import gitlab_native_wiki_cache_init as cache
        record = cycle.get('native_initialization_record')
        if not isinstance(record, dict):
            raise ValueError('Actual framed native initialization record required')
        import json
        checked = cache.parse_result('LAB_NATIVE_WIKI_CACHE_INIT_BEGIN\n' +
                                     json.dumps(record) + '\nLAB_NATIVE_WIKI_CACHE_INIT_END\n')
        actual = cache.verify_effects(cycle.get('columns_before'), cycle.get('columns_after'),
                    cycle['native_before_initialization'], cycle['protected_before'], checked)
        for columns, snapshot in ((cycle['columns_before'], cycle['native_before_initialization']),
                                  (cycle['columns_after'], cycle['protected_before'])):
            if (columns['columns'] != snapshot['projects']['columns']
                    or columns['row_count'] != snapshot['projects']['rows']):
                raise ValueError('Complete native project cell coverage differs from full snapshot')
        if cycle.get('native_initialization_effects') != actual:
            raise ValueError('Complete native initialization effects differ')
        refs = cycle.get('private_references')
        if not isinstance(refs, list) or not refs or len(refs) > 16:
            raise ValueError('Complete independent native reference set required')
        for spec in refs:
            primitive().validate(spec)
        if [primitive().digest(x) for x in refs] != contract['gitlab_native_read'].get('reference_sha256'):
            raise ValueError('Declared native reference identity differs')
        controls = cycle.get('controls')
        required = {'initial_no_op', 'wrong_target', '404', 'login'} | {
                    'positive_' + str(i) for i in range(len(refs))}
        if not isinstance(controls, dict) or set(controls) != required:
            raise ValueError('All native positive/wrong-object/404/login/no-op controls required')
        for name, value in controls.items():
            if not isinstance(value, dict) or not isinstance(value.get('site_origin'), str):
                raise ValueError('Actual control capture and original factory origin required')
            origin = urlsplit(value['site_origin'])
            if (origin.scheme not in ('http', 'https') or not origin.hostname
                    or origin.username is not None or origin.password is not None
                    or origin.path not in ('', '/') or origin.query or origin.fragment):
                raise ValueError('Exact credential-free native factory origin required')
            result = evaluate_any(refs, value.get('captures'), site_origin=value['site_origin'])
            expected = 'success' if name.startswith('positive_') else 'failure'
            if name.startswith('positive_'):
                index = int(name.removeprefix('positive_'))
                # Every allowed alternative needs its own native readability
                # proof. Repeating the first document must not admit the rest.
                if primitive().evaluate(refs[index], value['captures'][index],
                        site_origin=value['site_origin'])['status'] != 'success':
                    raise ValueError('Requested positive alternative was not actually readable')
            if name == 'initial_no_op':
                states = value['captures']
                if any(not isinstance(s, dict) or type(s.get('http_status')) is not int
                       or not 200 <= s['http_status'] < 300 or s.get('login_page') is not False
                       or s.get('error_page') is not False for s in states):
                    raise ValueError('Original first start was not a valid native page')
                expected = cycle.get('initial_goal_status')
                if expected not in ('success', 'failure'):
                    raise ValueError('Explicit measured initial goal status required')
            if result['status'] != expected:
                raise ValueError('Native control does not establish requested result: ' + name)
    for key in ('native_before_initialization', 'protected_before',
                'native_initialization_effects', 'private_references'):
        if cycles[0][key] != cycles[1][key]:
            raise ValueError('Independent native reset/reference differs: ' + key)
    return deepcopy(cycles[0]['private_references'])


class NativeReadHooks:
    def __init__(self, contract, proof, directory):
        self.references = require_admission(contract, proof)
        self.contract, self.proof = deepcopy(contract), deepcopy(proof)
        self.directory = Path(directory)
        self.prepared = False
        self.context = None
        self.site = None
        self.initial_page = None
        self.pages = set()
        self.popup_callbacks = {}
        self.clicks = None
        self.auth = None
        self.before = None
        self.scored = False

    def prepare(self, site, username):
        if self.prepared:
            raise ValueError('One native initialization per original reset required')
        import gitlab_native_wiki_cache_init as cache
        folder = self.directory / 'native-read-initialization'
        folder.mkdir(exist_ok=False)
        cold, baseline, effects = cache.initialize(site, folder)
        full_snapshot(cold); full_snapshot(baseline)
        expected = self.proof['cycles'][0]
        if (cold != expected['native_before_initialization']
                or baseline != expected['protected_before']
                or effects != expected['native_initialization_effects']):
            raise ValueError('Actual native initialized reset differs from both CPU controls')
        verified = [primitive().verify_reference(site, ref) for ref in self.references]
        atomic_write_json(self.directory / 'native-read-private-reference-before.json', verified)
        self.auth = auth_backup(site, username)
        self.before = baseline
        self.site = site
        self.prepared = True

    def attach(self, context):
        if not self.prepared or self.context is not None:
            raise ValueError('Prepared native read context required')
        self.context = context
        owner = self
        class BoundClicks(NavigationClicks):
            def record(self, source, event):
                if owner.allowed_page(source.get('page')):
                    super().record(source, event)
        self.clicks = BoundClicks(context)

    def allowed_page(self, page):
        # Binding callbacks must never issue synchronous browser commands.
        # Querying page.opener() here deadlocks while a click is still waiting
        # for the binding callback. Register the real native popup event once.
        return page is not None and page.context is self.context and page in self.pages

    def _register_page(self, page):
        if page.context is not self.context or page in self.pages:
            return
        self.pages.add(page)
        def opened(child):
            if self.allowed_page(page):
                self._register_page(child)
        self.popup_callbacks[page] = opened
        page.on('popup', opened)

    def observe_initial(self, page):
        if self.clicks is None or page.context is not self.context:
            raise ValueError('Bound original browser context required')
        if self.initial_page is not None:
            raise ValueError('One observed original initial page required')
        self.initial_page = page
        self._register_page(page)
        # Login/setup navigation never counts as an actor's requested click.
        self.clicks.reset()

    def capture_terminal(self, page, terminal):
        if not self.prepared or self.clicks is None or not self.allowed_page(page):
            raise ValueError('Prepared bound native read terminal required')
        captures = [{**deepcopy(terminal),
                     'gitlab_native_read': primitive().read_terminal(page, ref),
                     'navigation_click_evidence': self.clicks.snapshot()}
                    for ref in self.references]
        terminal['native_read_captures'] = captures
        atomic_write_json(self.directory / 'terminal-native-read.json', captures)

    def score_terminal(self, site, page, *, runtime_error=None):
        if not self.prepared or self.scored or site is not self.site:
            raise ValueError('One terminal judgment after verified native reset required')
        self.scored = True
        errors = []
        try:
            restore_auth_metadata(site, self.auth)
        except Exception as error:
            errors.append({'stage': 'bound_auth_metadata', 'exception_type': type(error).__name__})
        after = None
        try:
            after = protected_snapshot(site, self.directory / 'native-read-protected-progress.jsonl')
            full_snapshot(after)
        except Exception as error:
            errors.append({'stage': 'full16_terminal', 'exception_type': type(error).__name__})
        try:
            verified = [primitive().verify_reference(site, ref) for ref in self.references]
            atomic_write_json(self.directory / 'native-read-private-reference-after.json', verified)
        except Exception as error:
            errors.append({'stage': 'native_reference_terminal', 'exception_type': type(error).__name__})
        integrity = not errors and after == self.before
        atomic_write_json(self.directory / 'native-read-private-protection.json',
                          {'before': self.before, 'after': after, 'unchanged': integrity,
                           'errors': errors, 'complete16': True, 'columns_ignored': []})
        if runtime_error or errors:
            return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {},
                    'reason': 'Native runtime or independent reference incomplete'}, integrity
        judgment = evaluate_any(self.references, (page or {}).get('native_read_captures'),
                                site_origin=site.url)
        judgment['checks']['complete_native_state_unchanged'] = integrity
        if judgment['status'] != 'unknown' and not integrity:
            judgment.update(status='failure', reward=0.0)
        return judgment, integrity

    def close(self):
        for page, callback in self.popup_callbacks.items():
            page.remove_listener('popup', callback)
        self.popup_callbacks.clear()
        self.pages.clear()


def feedback(judgment):
    return {'status': judgment.get('status'), 'reward': judgment.get('reward'),
            'checks': {key: value for key, value in judgment.get('checks', {}).items()
                       if type(value) is bool},
            'scope': 'Declared local native document retrieval after termination.'}


def public_goal(contract):
    """Show the declared retrieval boundary without exposing private references."""
    if not enabled(contract):
        raise ValueError('Declared native read contract required')
    revision = contract.get('completion_revision')
    if not isinstance(revision, dict) or revision.get('version') != 'explicit-local-native-document-retrieval-v1':
        return contract['goal']
    if (not isinstance(revision, dict)
            or revision.get('version') != 'explicit-local-native-document-retrieval-v1'
            or revision.get('original_goal_preserved') is not True
            or revision.get('not_original_benchmark_equivalence') is not True
            or revision.get('public_completion_declaration') !=
              'Completion means retrieving and displaying the relevant local native document or source. Comprehension and natural-language answer correctness are not scored.'):
        raise ValueError('Exact declared training retrieval boundary required')
    return contract['goal'] + '\n' + revision['public_completion_declaration']
