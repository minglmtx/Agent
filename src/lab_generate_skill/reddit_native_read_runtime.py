"""Optional terminal-only native Reddit reading; no actor action policy.

Original post-author navigation accepts any actual activated native post and its
own author. Formatting accepts only declared native form/documentation scopes.
References and complete thirteen-table protection never enter actor feedback.
Capability captures cannot pass the formal same-hook admission gate.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import re
from urllib.parse import urlsplit

from . import reddit_post_author_navigation as author
from . import reddit_native_formatting_navigation as formatting
from . import reddit_native_read_protection as protection
from .io_utils import atomic_write_json
from .reddit_protected_chunks import validate_snapshot

VERSION = 'reddit-native-read-runtime-staged-v1'
PROOF_VERSION = 'reddit-native-read-full-hook-twofresh-v1'
SCOPE = 'Original local native public reading; complete declared thirteen tables.'
SHA = re.compile(r'[0-9a-f]{64}')
OTHER_FAMILIES = ('gitlab_native_read', 'native_csv_export', 'reddit_native_task',
    'reviewed_reddit_family', 'exact_forum_creation', 'query', 'membership',
    'preferences', 'cart', 'vote', 'catalog', 'search', 'wiki', 'submission',
    'forum_creation', 'account_change', 'checkout', 'order', 'map_export',
    'fork_creation', 'project_creation', 'ref_creation', 'clipboard',
    'repository_download', 'map_zoom', 'map_geolocation', 'todo',
    'review_creation', 'newsletter', 'issue_creation', 'group_creation',
    'native_reviews')
POST_CONTROLS = {'initial_no_op', 'positive', 'profile_without_post_link',
    'wrong_terminal_author', 'hidden_identity', 'missing_identity', '404', 'login'}
DOC_NEGATIVES = {'initial_no_op', 'hidden_panel', 'heading_only', 'wrong_syntax',
    '404', 'login'}


def enabled(contract):
    if 'reddit_native_read' not in contract:
        return False
    spec = contract['reddit_native_read']
    if (contract.get('domain') != 'reddit' or not isinstance(spec, dict)
            or contract.get('runtime_version') != VERSION
            or contract.get('eligible_for_training') is not False
            or contract.get('heldout_quarantine') is not False
            or contract.get('completion') != {}
            or any(key in contract for key in OTHER_FAMILIES)):
        raise ValueError('Separate original development native-read declaration required')
    if spec.get('kind') == 'post_author':
        if set(spec) != {'kind'}:
            raise ValueError('Post-author reading cannot fix a private post or author')
    elif spec.get('kind') == 'formatting_help':
        kinds = spec.get('form_kinds')
        if (set(spec) != {'kind', 'form_kinds'} or not isinstance(kinds, list)
                or not kinds or len(kinds) != len(set(kinds))
                or any(kind not in ('wiki', 'submission', 'comment') for kind in kinds)):
            raise ValueError('Explicit native formatting form alternatives required')
    else:
        raise ValueError('Unsupported native read family')
    binding(contract)
    return True


def binding(contract):
    keys = ('source_task_id', 'goal', 'start_path', 'recorded_start_paths', 'source_trace_ids')
    if (any(key not in contract for key in keys) or not isinstance(contract['goal'], str)
            or not contract['goal'] or contract.get('original_goal', contract['goal']) != contract['goal']
            or not isinstance(contract['source_task_id'], str) or not contract['source_task_id']
            or not isinstance(contract['recorded_start_paths'], list) or not contract['recorded_start_paths']
            or contract['start_path'] != contract['recorded_start_paths'][0]
            or not isinstance(contract['source_trace_ids'], list) or not contract['source_trace_ids']):
        raise ValueError('Complete unchanged original goal, first start and traces required')
    for path in contract['recorded_start_paths']:
        p = urlsplit(path)
        if (not isinstance(path, str) or not path.startswith('/') or path.startswith('//')
                or p.scheme or p.netloc or '\\' in path):
            raise ValueError('Original local recorded start paths required')
    if any(type(trace) not in (str, int) or isinstance(trace, bool) for trace in contract['source_trace_ids']):
        raise ValueError('Exact source trace identities required')
    return {key: deepcopy(contract[key]) for key in keys} | {'reddit_native_read': deepcopy(contract['reddit_native_read'])}


def require_original_binding(contract, original, inventory):
    enabled(contract)
    if not isinstance(original, dict) or {k: v for k, v in contract.items() if k != 'admission_result'} != original:
        raise ValueError('Native reading changed the CPU binding')
    def path(value):
        p = urlsplit(value)
        return (p.path or '/') + ('?' + p.query if p.query else '') + ('#' + p.fragment if p.fragment else '')
    if (not isinstance(inventory, dict) or inventory.get('domain') != 'reddit'
            or inventory.get('task_id') != contract['source_task_id']
            or inventory.get('heldout_quarantine') is not False
            or inventory.get('goal') != contract['goal']
            or inventory.get('source_trace_ids') != contract['source_trace_ids']
            or [path(value) for value in inventory.get('recorded_start_urls', [])] != contract['recorded_start_paths']):
        raise ValueError('Authoritative original goal/start/trace mapping differs')


def validate_complete_snapshot(value):
    if (not isinstance(value, dict) or set(value) != {'version', 'twelve_task_tables',
            'submissions', 'users_only_ignored_column'} or value['version'] != protection.VERSION
            or value['users_only_ignored_column'] != 'last_seen'):
        raise ValueError('Versioned complete thirteen-table protection required')
    validate_snapshot(value['twelve_task_tables'])
    row = value['submissions']
    if (not isinstance(row, dict) or set(row) != {'count', 'columns', 'key', 'sha256'}
            or type(row['count']) is not int or row['count'] < 0 or row['key'] != ['id']
            or not isinstance(row['columns'], list) or not row['columns'] or 'id' not in row['columns']
            or any(not isinstance(x, str) or not re.fullmatch('[a-z][a-z0-9_]*', x) for x in row['columns'])
            or len(row['columns']) != len(set(row['columns']))
            or not isinstance(row['sha256'], str) or not SHA.fullmatch(row['sha256'])
            or row['count'] == 0 and row['sha256'] != hashlib.sha256(b'').hexdigest()):
        raise ValueError('Complete native submission columns, primary key and row coverage required')
    return value


def _refs(records):
    if not isinstance(records, list):
        raise ValueError('Complete terminal native reference rows required')
    result = {}
    for row in records:
        if not isinstance(row, dict) or type(row.get('post_id')) is not int or row['post_id'] in result:
            raise ValueError('Unique actual observed native post references required')
        result[row['post_id']] = row
    return result


def evaluate_terminal(contract, terminal, references, *, site_origin):
    enabled(contract); author.origin(site_origin)
    kind = contract['reddit_native_read']['kind']
    if not isinstance(terminal, dict) or terminal.get('runtime_version') != VERSION:
        raise ValueError('Actual bound terminal native-read capture required')
    if kind == 'post_author':
        mapped = _refs(references)
        capture = terminal.get('public_events')
        if not isinstance(capture, dict) or not isinstance(capture.get('events'), list):
            raise ValueError('Complete initialized bound public event list required')
        ids = {author.observed_association(event, site_origin=site_origin)['post_id'] for event in capture['events']}
        if set(mapped) != ids:
            raise ValueError('Independent references must match exactly the actually observed posts')
        checks = author.capture_checks(capture, terminal.get('public_terminal'),
                                       mapped, site_origin=site_origin)
    else:
        if (not isinstance(references, list) or len(references) != len(contract['reddit_native_read']['form_kinds'])
                or [x.get('spec', {}).get('form_kind') for x in references] != contract['reddit_native_read']['form_kinds']):
            raise ValueError('Every declared independent native documentation alternative required')
        alternatives = []
        for reference in references:
            if not isinstance(reference, dict) or set(reference) != {'spec', 'native_sources'}:
                raise ValueError('Actual shipped native documentation reference required')
            sources = reference['native_sources']
            if (not isinstance(sources, dict) or set(sources) != {'template_sha256', 'translation_sha256', 'translations'}
                    or sources['template_sha256'] != protection.MARKDOWN_TEMPLATE_SHA
                    or sources['translation_sha256'] != protection.MARKDOWN_TRANSLATIONS_SHA):
                raise ValueError('Pinned native documentation source identity differs')
            keys = ('markdown.link', 'markdown.forum', 'markdown.user', 'markdown.wiki_page')
            translations = sources['translations']
            if (not isinstance(translations, dict) or set(translations) != set(keys)
                    or any(not isinstance(translations[k], str) or not translations[k] for k in keys)):
                raise ValueError('Complete shipped native documentation translations required')
            link, forum, user, wiki = [translations[k] for k in keys]
            suffix = f'/f/{forum} /u/{user} /w/{wiki}'
            expected = {'form_kind': reference['spec'].get('form_kind'), 'required_rows': [{
                'feature': link + ' ' + suffix,
                'syntax': f'[{link}](http://example.com) ' + suffix}]}
            if reference['spec'] != expected:
                raise ValueError('Documentation specification differs from pinned native template and translations')
            alternatives.append(formatting.checks(reference['spec'], terminal.get('public_terminal'), site_origin=site_origin))
        checks = next((row for row in alternatives if all(row.values())), alternatives[0])
    return {'version': VERSION, 'status': 'success' if all(checks.values()) else 'failure',
            'reward': float(all(checks.values())), 'checks': checks}


def same_method_provenance():
    names = ('prepare', 'attach', 'observe_initial', 'capture_terminal', 'score_terminal', 'close')
    return {'lifecycle_methods': list(names), 'inherited_identical_methods': True,
        'runtime_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'author_source_sha256': hashlib.sha256(Path(author.__file__).read_bytes()).hexdigest(),
        'formatting_source_sha256': hashlib.sha256(Path(formatting.__file__).read_bytes()).hexdigest(),
        'protection_source_sha256': hashlib.sha256(Path(protection.__file__).read_bytes()).hexdigest(),
        'submission_reader_source_sha256': hashlib.sha256(Path(__file__).with_name('reddit_submission_snapshot_stream.py').read_bytes()).hexdigest(),
        'reader_equivalence_source_sha256': hashlib.sha256(Path(__file__).with_name('reddit_reader_equivalence.py').read_bytes()).hexdigest()}


def compatible_method_provenance(recorded):
    current=same_method_provenance()
    if recorded==current:return True
    from .reddit_reader_equivalence import matches_historical_reader_provenance
    return matches_historical_reader_provenance(recorded,current)


def require_admission(contract, proof):
    enabled(contract)
    if (not isinstance(proof, dict) or proof.get('version') != PROOF_VERSION
            or proof.get('scope') != SCOPE or proof.get('original_binding') != binding(contract)
            or proof.get('actor_attempts') != 0 or type(proof.get('actor_attempts')) is not int
            or proof.get('api_calls') != 0 or type(proof.get('api_calls')) is not int
            or not compatible_method_provenance(proof.get('same_method_provenance'))):
        raise ValueError('Unchanged original zero-model formal full-hook proof required')
    cycles = proof.get('cycles')
    if not isinstance(cycles, list) or len(cycles) != 2 or any(not isinstance(c, dict) for c in cycles):
        raise ValueError('Two cold same-hook native cycles required')
    ids = [c.get('fresh_instance_id') for c in cycles]
    if any(not isinstance(x, str) or not SHA.fullmatch(x) for x in ids) or len(set(ids)) != 2:
        raise ValueError('Distinct real cold factory instance identities required')
    expected_names = POST_CONTROLS if contract['reddit_native_read']['kind'] == 'post_author' else DOC_NEGATIVES | {
        'positive_' + kind for kind in contract['reddit_native_read']['form_kinds']}
    for cycle in cycles:
        selected = cycle.get('initial_fingerprint')
        if (not isinstance(selected, str) or not SHA.fullmatch(selected)
                or cycle.get('final_fingerprint') != selected):
            raise ValueError('Unchanged original selected-state fingerprint required')
        baseline = validate_complete_snapshot(cycle.get('protected_before'))
        if validate_complete_snapshot(cycle.get('protected_after')) != baseline:
            raise ValueError('Full thirteen-table cold restoration differs')
        initial = cycle.get('initial_page')
        if (not isinstance(initial, dict) or type(initial.get('http_status')) is not int
                or not 200 <= initial['http_status'] < 300 or initial.get('login_page') is not False
                or initial.get('error_page') is not False
                or _page_path(initial.get('url'), cycle.get('site_origin')) != contract['start_path']):
            raise ValueError('Actual unchanged original first-start page required')
        controls = cycle.get('controls')
        if not isinstance(controls, dict) or set(controls) != expected_names:
            raise ValueError('Every native positive and public negative control required')
        for name, record in controls.items():
            if (not isinstance(record, dict) or record.get('hook_version') != VERSION
                    or record.get('hook_lifecycle') != ['prepare', 'attach', 'observe_initial', 'capture_terminal', 'score_terminal']
                    or record.get('site_origin') != cycle.get('site_origin')
                    or record.get('bound_page_verified') is not True
                    or record.get('fresh_auth_context_no_cookies') is not True
                    or record.get('original_start_restored') is not True
                    or not compatible_method_provenance(record.get('same_method_provenance'))
                    or validate_complete_snapshot(record.get('protected_before')) != baseline
                    or validate_complete_snapshot(record.get('protected_after')) != baseline
                    or record.get('selected_before') != selected
                    or record.get('selected_after') != selected
                    or record.get('integrity') is not True):
                raise ValueError('Actual complete same-hook cold lifecycle receipt required')
            result = evaluate_terminal(contract, record.get('terminal'), record.get('private_references'),
                                       site_origin=record['site_origin'])
            if record.get('judgment') != result or result['status'] != ('success' if name == 'positive' or name.startswith('positive_') else 'failure'):
                raise ValueError('Formal hook control does not reproduce requested native result: ' + name)
            if name.startswith('positive_'):
                kind = name.removeprefix('positive_')
                index = contract['reddit_native_read']['form_kinds'].index(kind)
                if not all(formatting.checks(record['private_references'][index]['spec'],
                    record['terminal']['public_terminal'], site_origin=record['site_origin']).values()):
                    raise ValueError('Each allowed native documentation surface needs its own positive')
    if cycles[0]['initial_fingerprint'] != cycles[1]['initial_fingerprint']:
        raise ValueError('Cold original selected-state baseline differs')
    if cycles[0]['protected_before'] != cycles[1]['protected_before']:
        raise ValueError('Cold native thirteen-table baselines differ')
    return deepcopy(cycles[0]['protected_before'])


def _page_path(value, site_origin):
    author.origin(site_origin)
    u = urlsplit(value)
    if (u.scheme, u.netloc) != author.origin(site_origin) or u.username is not None or u.password is not None:
        raise ValueError('Actual original first-start factory page required')
    return (u.path or '/') + ('?' + u.query if u.query else '') + ('#' + u.fragment if u.fragment else '')


class _NativeReadLifecycle:
    """Shared exact lifecycle; private CPU controls supply measured cold state.

    Production always uses the proof-gated subclass below. This core does not
    create, bind, register, or claim any normal admission.
    """
    def __init__(self, contract, baseline, selected_baseline, directory):
        enabled(contract)
        self.baseline = deepcopy(validate_complete_snapshot(baseline))
        if not isinstance(selected_baseline, str) or not SHA.fullmatch(selected_baseline):
            raise ValueError('Independently measured cold selected-state fingerprint required')
        self.expected_selected = selected_baseline
        self.contract = deepcopy(contract)
        self.directory = Path(directory); self.site = None; self.context = None
        self.pages = set(); self.popups = {}; self.initial_page = None; self.collector = None
        self.references_before = None; self.terminal = None; self.scored = False; self.events = []
        self.selected_before = None
        self.last_receipt = None

    def prepare(self, site, username):
        if self.site is not None or site.domain != 'reddit' or not isinstance(username, str) or not username:
            raise ValueError('One native original Reddit reset required')
        author.origin(site.url)
        current = protection.complete_snapshot(site, self.directory / 'native-reddit-read-protected-progress.jsonl')
        validate_complete_snapshot(current)
        if current != self.baseline:
            raise ValueError('Actual cold native reset differs from both full-hook proofs')
        self.selected_before = site.fingerprint()
        if self.selected_before != self.expected_selected:
            raise ValueError('Actual original selected-state baseline differs from both controls')
        self.site = site; self.events.append('prepare')
        if self.contract['reddit_native_read']['kind'] == 'formatting_help':
            self.references_before = [protection.formatting_reference(site, kind)
                for kind in self.contract['reddit_native_read']['form_kinds']]
            atomic_write_json(self.directory / 'native-reddit-read-private-reference-before.json', self.references_before)
        atomic_write_json(self.directory / 'native-reddit-read-protected-before.json', current)

    def allowed_page(self, page):
        return page is not None and page.context is self.context and page in self.pages

    def _register_page(self, page):
        if page.context is not self.context or page in self.pages:
            return
        self.pages.add(page)
        def opened(child):
            if self.allowed_page(page):
                self._register_page(child)
        self.popups[page] = opened; page.on('popup', opened)

    def attach(self, context):
        if self.site is None or self.context is not None:
            raise ValueError('Cold prepared source-local browser context required')
        self.context = context; self.events.append('attach')
        if self.contract['reddit_native_read']['kind'] == 'post_author':
            owner = self
            class BoundAuthor(author.PassivePostAuthorCapture):
                def _record(self, source, event):
                    if isinstance(source, dict) and owner.allowed_page(source.get('page')):
                        super()._record(source, event)
            self.collector = BoundAuthor(self.site.url); self.collector.attach(context)

    def observe_initial(self, page):
        if self.context is None or page.context is not self.context or self.initial_page is not None:
            raise ValueError('One actual original rollout Page required')
        if _page_path(page.url, self.site.url) != self.contract['start_path']:
            raise ValueError('Observe the unchanged original first-start document')
        self.initial_page = page; self._register_page(page)
        if self.collector is not None:
            self.collector.clear()
        self.events.append('observe_initial')

    def capture_terminal(self, page, terminal):
        if self.scored or self.terminal is not None or not self.allowed_page(page):
            raise ValueError('One bound original or native child terminal Page required')
        if not isinstance(terminal, dict) or terminal.get('url') != page.url:
            raise ValueError('Actual terminal document identity required')
        fields = {k: terminal[k] for k in ('http_status', 'login_page', 'error_page')}
        if self.collector is not None:
            public = page.evaluate(author.READ_PROFILE) | fields
            value = {'runtime_version': VERSION, 'public_terminal': public,
                     'public_events': self.collector.read()}
        else:
            public = formatting.read(page) | fields
            value = {'runtime_version': VERSION, 'public_terminal': public}
        if public['url'] != page.url:
            raise ValueError('Native public reader changed terminal document')
        self.terminal = deepcopy(value); self.events.append('capture_terminal')
        terminal['reddit_native_read_capture'] = value
        atomic_write_json(self.directory / 'terminal-reddit-native-read-public.json', value)

    def score_terminal(self, site, terminal, *, runtime_error=None):
        if site is not self.site or self.scored:
            raise ValueError('One judgment on the actual prepared native factory required')
        self.scored = True; self.events.append('score_terminal')
        after = None; refs = None; error = None; selected_after = None
        try:
            after = protection.complete_snapshot(site, self.directory / 'native-reddit-read-protected-progress.jsonl')
            validate_complete_snapshot(after)
            selected_after = site.fingerprint()
            if self.terminal is None or terminal.get('reddit_native_read_capture') != self.terminal:
                raise ValueError('Complete bound terminal capture missing or changed')
            if self.collector is not None:
                captured = self.terminal['public_events']; mapped = {}
                for event in captured['events']:
                    row = author.verify_reference(site, event)
                    if row['post_id'] in mapped and mapped[row['post_id']] != row:
                        raise ValueError('Native post reference changed during terminal verification')
                    mapped[row['post_id']] = row
                refs = list(mapped.values())
            else:
                refs = [protection.formatting_reference(site, kind)
                        for kind in self.contract['reddit_native_read']['form_kinds']]
                if refs != self.references_before:
                    raise ValueError('Shipped documentation reference changed during rollout')
            result = evaluate_terminal(self.contract, self.terminal, refs, site_origin=site.url)
        except Exception as exc:
            error = type(exc).__name__
            result = {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {},
                      'reason': 'Bound native terminal or complete private verification is unavailable.'}
        integrity = error is None and after == self.baseline and selected_after == self.selected_before
        if runtime_error:
            result = {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {},
                      'reason': 'Runtime ended before complete native verification.'}
        elif result['status'] != 'unknown' and not integrity:
            result.update(status='failure', reward=0.0)
        self.last_receipt = {'hook_version': VERSION, 'hook_lifecycle': list(self.events),
            'site_origin': site.url, 'bound_page_verified': self.terminal is not None,
            'protected_before': self.baseline, 'protected_after': after,
            'selected_before': self.selected_before, 'selected_after': selected_after,
            'terminal': self.terminal, 'private_references': refs, 'judgment': result,
            'integrity': integrity, 'diagnostic_exception_type': error}
        atomic_write_json(self.directory / 'native-reddit-read-full-hook-receipt.json', self.last_receipt)
        return result, integrity

    def close(self):
        for page, callback in self.popups.items():
            page.remove_listener('popup', callback)
        self.popups.clear(); self.pages.clear()


class RedditNativeReadHooks(_NativeReadLifecycle):
    """The only shared runtime constructor; complete admission is mandatory."""
    def __init__(self, contract, proof, directory):
        baseline = require_admission(contract, proof)
        self.proof = deepcopy(proof)
        super().__init__(contract, baseline, proof['cycles'][0]['initial_fingerprint'], directory)


def feedback(judgment):
    return {'status': judgment.get('status'), 'reward': judgment.get('reward'),
            'checks': {name: value for name, value in judgment.get('checks', {}).items() if type(value) is bool},
            'scope': 'Terminal native public reading with independent complete protection.',
            'private_reference_values_provided': False, 'action_sequence_provided': False}
