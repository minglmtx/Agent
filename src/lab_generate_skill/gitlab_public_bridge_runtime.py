"""Candidate ordinary-factory terminal hooks for three native GitLab kinds.

The public task object is shared by generator/actor. References and complete
guards are private. New native admission is still required before training.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from .source_revision_binding import binding, fingerprint, require_source_binding
from .io_utils import atomic_write_json
from .gitlab_public_bridge_native import (VERSION as NATIVE_VERSION, KINDS,
    public_key, collect, evaluate, feedback, digest, integrity)

VERSION = 'gitlab-public-bridge-runtime-candidate-v1'
PROOF_VERSION = 'gitlab-public-bridge-normal-controls-candidate-v1'
SHA = re.compile('[0-9a-f]{64}')
AUTHORIZED_TARGET_WRITES = True


def private_json(path, value):
    path = Path(path); atomic_write_json(path, value); path.chmod(0o600)


def contract_from_case(case):
    """Only explicit public determinization, retaining all original lineage."""
    c = {k: deepcopy(case[k]) for k in ('source_task_id', 'task_id', 'domain',
        'original_goal', 'goal', 'start_path', 'recorded_start_urls',
        'recorded_start_paths', 'source_trace_ids', 'task_text_changed',
        'goal_revision', 'start_revision', 'heldout_quarantine',
        'eligible_for_training', 'public_parameters', 'public_task_input')}
    for key in ('goal_revision', 'start_revision'):
        if c[key] is not None:
            for flag in list(c[key]):
                if flag.startswith('equivalent_to_original'):c[key].pop(flag)
            c[key]['equivalent_to_original_goal' if key=='goal_revision' else 'equivalent_to_original_start'] = False
    c['gitlab_public_bridge'] = {'version': VERSION,
        'kind': case['bridge_contract']['kind'],
        'declaration': deepcopy(case['bridge_contract']['public_parameters'])}
    c['completion'] = {'family': 'gitlab_public_bridge'}
    c['is_explicit_derivative'] = True
    c['original_benchmark_equivalence'] = False
    enabled(c)
    return c


def enabled(c):
    if 'gitlab_public_bridge' not in c:
        return False
    s = c['gitlab_public_bridge']
    if (c.get('domain') != 'gitlab' or not isinstance(s, dict)
            or set(s) != {'version', 'kind', 'declaration'} or s['version'] != VERSION
            or s['kind'] not in KINDS or c.get('completion') != {'family': 'gitlab_public_bridge'}
            or c.get('is_explicit_derivative') is not True
            or c.get('original_benchmark_equivalence') is not False
            or c.get('eligible_for_training') is not False
            or c.get('heldout_quarantine') is not False):
        raise ValueError('Explicit unadmitted native public bridge contract required')
    binding(c)
    params = c.get('public_parameters')
    if not isinstance(params, dict) or s['declaration'] != params:
        raise ValueError('Exact supplied public task parameters required')
    if c.get('public_task_input') != {'goal': c['goal'], 'public_parameters': params}:
        raise ValueError('Generator and actor must share the same supplied public task input')
    if s['kind'] == 'native_topic_filter':
        if set(params) != {'topic', 'collection'} or params['collection'] != 'non_archived_explore' or not isinstance(params['topic'], str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}', params['topic']):
            raise ValueError('Exact native Explore topic scope required')
    elif s['kind'] == 'native_profile_ssh_key':
        if set(params) != {'public_key', 'title'} or not isinstance(params['title'], str) or not params['title'].strip() or '\n' in params['title']:
            raise ValueError('Supplied public key and title required')
        public_key(params['public_key'])
    elif set(params) != {'name'} or not isinstance(params['name'], str) or not params['name'].strip() or len(params['name']) > 200 or '\n' in params['name']:
        raise ValueError('One supplied target profile full name required')
    other = ('query', 'gitlab_native_read', 'gitlab_grouped_goal', 'gitlab_boundary_goal',
             'gitlab_persisted_goal', 'preferences', 'clipboard', 'repository_download')
    if any(c.get(k) for k in other):
        raise ValueError('Only one normal completion protocol may be enabled')
    return True


def public_goal(c):
    enabled(c)
    # Same canonical public object and renderer as every other candidate
    # family. The root frozen worker supplies common-candidate on sys.path.
    from public_task_input import render
    return render(c)


def fields(c):
    enabled(c)
    return []


def require_original_binding(c, original, inventory):
    enabled(c)
    return require_source_binding(c, original, inventory, domain='gitlab')


def _expected_controls(kind):
    return ({'initial_no_op', 'positive', 'wrong_filter', 'partial_collection', '404', 'login'}
            if kind == 'native_topic_filter' else
            {'initial_no_op', 'positive', 'unsaved', 'wrong_account', 'wrong_value', 'other_field', '404', 'login'})


def partial_collection_applicability(c, positive):
    """A native single-page positive makes pagination truncation inapplicable.

    This is derived from full native relation + actual positive capture, never
    a count assumption or passed flag. Partial membership still fails evaluate.
    """
    enabled(c)
    if c['gitlab_public_bridge']['kind'] != 'native_topic_filter':
        return None
    if not isinstance(positive, dict):
        return {'status': 'required', 'reason': 'No complete native positive exists'}
    try:
        actual = evaluate(c, positive['initial'], positive['final'], positive['captures'],
                          positive['terminal'], site_origin=positive['site_origin'])
        terminal = positive['terminal']
        complete = (actual['status'] == 'success'
            and terminal.get('pagination_pages') == [1] and terminal.get('page_number') == 1
            and len(terminal.get('project_paths', [])) == len(set(terminal.get('project_paths', [])))
            and set(terminal.get('project_paths', [])) == {r['path'] for r in positive['initial']['state']['projects']})
    except (KeyError, TypeError, ValueError):
        complete = False
    if not complete:
        return {'status': 'required', 'reason': 'Native multi-page or incomplete collection requires actual partial control'}
    # Explicitly offline mutation of the captured candidate member set. This
    # does not pretend a nonexistent browser page was visited. Re-evaluate the
    # same complete independent native relation to prove a missing item fails.
    partial = deepcopy(terminal)
    partial['project_paths'] = partial['project_paths'][1:]
    rejected = evaluate(c, positive['initial'], positive['final'], [partial], partial,
                        site_origin=positive['site_origin'])
    if rejected['status'] != 'failure':
        raise ValueError('Single-page gate requires independent offline missing-member rejection')
    return {'status': 'not_applicable',
            'reason': 'Actual complete native topic collection is one page; pagination truncation cannot occur',
            'positive_native_evidence_sha256': digest({k: positive[k] for k in
                ('initial', 'final', 'captures', 'terminal', 'site_origin')}),
            'offline_partial_membership_rejection_required': True,
            'offline_partial_membership_rejection': {
                'mode': 'offline_mutation_of_captured_member_set',
                'missing_members': 1, 'judgment': rejected,
                'native_control_claimed': False}}


def _cycle_controls(c, cycle):
    expected = _expected_controls(c['gitlab_public_bridge']['kind'])
    if c['gitlab_public_bridge']['kind'] == 'native_topic_filter':
        actual = partial_collection_applicability(c, cycle.get('controls', {}).get('positive'))
        if cycle.get('partial_collection_applicability') != actual:
            raise ValueError('Native partial-control applicability must be recomputed from complete positive evidence')
        if actual['status'] == 'not_applicable':
            expected = expected - {'partial_collection'}
    return expected


def require_admission(c, p):
    enabled(c)
    if (not isinstance(p, dict) or p.get('version') != PROOF_VERSION
            or p.get('contract_fingerprint') != fingerprint(c)
            or p.get('original_binding') != binding(c)
            or p.get('actor_attempts') != 0 or type(p.get('actor_attempts')) is not int
            or p.get('api_calls') != 0 or type(p.get('api_calls')) is not int
            or p.get('formal_preinference_lifecycle_verified') is not True):
        raise ValueError('Complete current-source zero-model ordinary native proof required')
    cycles = p.get('cycles')
    if not isinstance(cycles, list) or len(cycles) != 2:
        raise ValueError('Two independent cold source resets required')
    ids = [r.get('fresh_instance_id') for r in cycles]
    if any(not SHA.fullmatch(x or '') for x in ids) or len(set(ids)) != 2:
        raise ValueError('Distinct independent cold instance IDs required')
    for cycle in cycles:
        controls = _cycle_controls(c, cycle)
        if (cycle.get('reset_baseline_reproduced') is not True
                or cycle.get('original_first_start_preserved') is not True
                or set(cycle.get('controls', {})) != controls):
            raise ValueError('All complete ordinary positive/negative/reset controls required')
        for name, record in cycle['controls'].items():
            from gitlab_browser_lifecycle import normal_lifecycle
            if (not normal_lifecycle(record.get('events'))
                    or record.get('normal_lifecycle_verified') is not True
                    or record.get('private_feedback_clean') is not True
                    or record.get('actual_issued_ax_recorded') is not True
                    or record.get('initial') != cycle.get('initial')
                    or record.get('public_task_input') != c['public_task_input']):
                raise ValueError('Original source/current shared ordinary lifecycle mismatch')
            actual = evaluate(c, record['initial'], record['final'], record['captures'],
                              record['terminal'], site_origin=record['site_origin'])
            expected = 'success' if name == 'positive' else 'failure'
            if actual['status'] != expected or record.get('judgment') != actual:
                raise ValueError('Native ordinary terminal control does not establish ' + name)
            # Deliberately corrupting unrelated state is a negative control;
            # it may fail integrity, but that must be explicit in original
            # evidence, never silently treated as a normal admitted rollout.
            if record.get('terminal_integrity') is not integrity(c, record['initial'], record['final']):
                raise ValueError('Actual complete native guard receipt differs')
    if cycles[0]['initial'] != cycles[1]['initial']:
        raise ValueError('Complete cold reset/account/reference/full16/refs differs')
    return deepcopy(cycles[0]['initial'])


def capture_page(page, statuses):
    """Read current native DOM/AX; no hidden reference data or browser actions."""
    state = page.evaluate(r'''() => {
      const shown=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
      const fields=[...document.querySelectorAll('input[name],select[name]')].filter(e=>['topic','tag'].includes(e.name));
      const controls=fields.map(e=>({name:e.name,value:e.value,visible:shown(e),
        selectedLabels:e.tagName==='SELECT'?[...e.selectedOptions].map(o=>o.textContent.trim()):[],
        labels:[...document.querySelectorAll('label')].filter(x=>x.htmlFor===e.id).map(x=>x.innerText.trim())}));
      const pagination=[...document.querySelectorAll('a.page-link[href],.pagination a[href]')].filter(shown).map(e=>e.getAttribute('href'));
      return {url:location.href,account_id:window.gon?.current_user_id,
        controls, pagination,
        project_paths:[...document.querySelectorAll('.project-row')].filter(shown).map(e=>e.querySelector('a.project[href]')?.getAttribute('href')),
        body:document.body.innerText,
        profile_name:[...document.querySelectorAll('input[name="user[name]"]')].filter(shown).map(e=>e.value)};
    }''')
    url = state['url']; parsed = urlsplit(url); query = parse_qs(parsed.query, keep_blank_values=True)
    status = statuses.get(url, {}).get('status')
    document = statuses.get(url, {})
    state.update(http_status=status, login_page=parsed.path in ('/users/sign_in', '/login'),
        error_page=parsed.scheme.startswith('chrome-error') or type(status) is int and status >= 400,
        document_get_200=document.get('get_200') is True)
    cdp = page.context.new_cdp_session(page)
    try:
        nodes = cdp.send('Accessibility.getFullAXTree')['nodes']
        ax = [n.get('name', {}).get('value', '') for n in nodes if not n.get('ignored')]
    finally:
        cdp.detach()
    state['issued_ax'] = ax
    controls = [x for x in state['controls'] if isinstance(x.get('value'), str) and x['value']]
    selected = controls[0] if len(controls) == 1 else None
    native = selected is not None and (selected['visible'] or any(selected['value'] in str(x) for x in ax))
    state.update(native_topic_control=native,
        topic_field=selected['name'] if selected else None,
        topic_value=selected['value'] if selected else None,
        issued_ax_contains_control=selected is not None and any(selected['value'] in str(x) or any(label in str(x) for label in selected['labels'] + selected['selectedLabels']) for x in ax),
        native_control_query_agrees=selected is not None and query.get(selected['name']) == [selected['value']])
    number = query.get('page', ['1'])
    state['page_number'] = int(number[0]) if len(number) == 1 and number[0].isdecimal() and int(number[0]) > 0 else None
    pages = {state['page_number']} if state['page_number'] else set()
    for link in state.pop('pagination'):
        u = urlsplit(link); params = parse_qs(u.query, keep_blank_values=True)
        page_number = params.get('page', ['1'])
        if u.path == parsed.path and len(page_number) == 1 and page_number[0].isdecimal():
            pages.add(int(page_number[0]))
    state['pagination_pages'] = sorted(pages)
    state['project_paths'] = [urlsplit(p).path.strip('/') if isinstance(p, str) and p.startswith('/') and not p.startswith('//') else None for p in state['project_paths']]
    return state


class PublicBridgeHooks:
    def __init__(self, c, proof, directory, *, development_controls=False):
        enabled(c)
        self.contract = deepcopy(c); self.directory = Path(directory)
        self.development_controls = development_controls
        self.expected = None if development_controls else require_admission(c, proof)
        if development_controls and proof is not None:
            raise ValueError('Development native controls must not import another source proof')
        self.prepared = False; self.context = None; self.initial_page = None
        self.scored = False; self.site = None; self.captures = []; self.statuses = {}
        self.events = []; self.listener = None
        self.issued = []

    def prepare(self, site, username):
        if self.prepared or site.domain != 'gitlab':
            raise ValueError('One current-source native initial reset required')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        self.initial = collect(site, self.contract, username, self.directory / 'initial-native-read-progress.jsonl')
        if self.expected is not None and self.initial != self.expected:
            raise ValueError('Actual current complete native source reset differs from admitted two-cold baseline')
        self.username = username; self.site = site; self.prepared = True
        self.events.append('prepare'); private_json(self.directory / 'private-bridge-initial.json', self.initial)

    def attach(self, context):
        if not self.prepared or self.context is not None:
            raise ValueError('One prepared ordinary browser context required')
        self.context = context
        origin = urlsplit(self.site.url)
        def response(value):
            request = value.request
            u = urlsplit(value.url)
            if (u.scheme, u.netloc) != (origin.scheme, origin.netloc):
                return
            if request.resource_type == 'document':
                self.statuses[value.url] = {'status': value.status,
                    'get_200': request.method == 'GET' and value.status == 200}
        self.listener = response; context.on('response', response); self.events.append('attach')

    def observe_initial(self, page):
        if self.initial_page is not None or page.context is not self.context or page.url != self.site.url + self.contract['start_path']:
            raise ValueError('Original first start/current ordinary page must be preserved')
        self.initial_page = page; self.events.append('observe_initial'); self.record(page)

    def record(self, page):
        if self.initial_page is None or page.context is not self.context or self.scored:
            raise ValueError('Actual current ordinary page observation required')
        state = capture_page(page, self.statuses)
        self.captures.append(state); self.events.append('record')
        private_json(self.directory / 'private-bridge-observations.json', self.captures)

    def acknowledge_issued(self, actual_ax):
        """The ordinary runner reports the AX text actually sent to the actor."""
        if not self.captures or not isinstance(actual_ax, str) or not actual_ax.strip():
            raise ValueError('Actual ordinary issued AX observation required')
        current = self.captures[-1]
        current['actor_issued_ax'] = actual_ax
        current['issued_ax_contains_control'] = (isinstance(current.get('topic_value'), str)
            and bool(current['topic_value']) and current['topic_value'] in actual_ax)
        self.issued.append({'url': current['url'], 'sha256': digest(actual_ax)})
        private_json(self.directory / 'private-bridge-observations.json', self.captures)

    def capture_terminal(self, page, terminal):
        # Do not manufacture another "issued" observation at episode close.
        # Refresh native terminal document while retaining only a genuinely
        # issued observation of this same URL/native control state.
        state = capture_page(page, self.statuses)
        previous = next((r for r in reversed(self.captures) if r['url'] == state['url']
            and r.get('topic_value') == state.get('topic_value')
            and isinstance(r.get('actor_issued_ax'), str)), None)
        state['issued_ax_contains_control'] = previous is not None and previous.get('issued_ax_contains_control') is True
        if previous is not None:
            state['actor_issued_ax'] = previous['actor_issued_ax']
        self.captures.append(state); self.terminal = deepcopy(state)
        terminal['gitlab_public_bridge_terminal'] = {'captured_after_termination': True}
        self.events.append('capture_terminal')

    def score_terminal(self, site, page, *, runtime_error=None):
        # Common runner closes BrowserGym before final native scoring; the
        # complete live DOM capture was retained by capture_terminal.
        if not self.prepared or self.scored or site is not self.site or not isinstance(page, dict):
            raise ValueError('One final-only ordinary native judgment required')
        self.scored = True; errors = []; self.final = None
        try:
            self.final = collect(site, self.contract, self.username, self.directory / 'final-native-read-progress.jsonl')
        except Exception as error:
            errors.append({'exception_type': type(error).__name__})
        terminal = getattr(self, 'terminal', None)
        result = evaluate(self.contract, self.initial, self.final, self.captures, terminal,
            site_origin=site.url, runtime_error=runtime_error or bool(errors))
        preserved = not errors and integrity(self.contract, self.initial, self.final)
        self.events.append('score_terminal')
        private_json(self.directory / 'private-bridge-protection.json', {
            'initial': self.initial, 'final': self.final, 'terminal': terminal,
            'captures': self.captures, 'integrity': preserved, 'capture_errors': errors,
            'judgment': result, 'events': self.events, 'issued': self.issued})
        return result, preserved

    def close(self):
        from gitlab_browser_lifecycle import bridge_close
        bridge_close(self)


def make_hooks(c, proof, directory, *, development_controls=False):
    return PublicBridgeHooks(c, proof, directory, development_controls=development_controls)


def make_session(site, contract, directory, auth, *, hooks, **kwargs):
    """The real installed BrowserGym factory and unchanged observation/action flow."""
    import run_site_navigation_once as runner
    from public_task_input import install_normal_goal_adapter
    from gitlab_browser_lifecycle import install
    install(runner)
    # Task.setup reads runner.public_goal at reset time. This idempotent
    # common adapter therefore changes the actually issued BrowserGym goal,
    # not merely the BrowserTask construction argument.
    install_normal_goal_adapter(runner)
    ordinary_factory = runner.make_session
    if not isinstance(hooks, PublicBridgeHooks) or not hooks.prepared or hooks.contract != contract:
        raise ValueError('Exactly bound prepared native bridge hooks required')
    if 'native_read_hooks' in kwargs:
        raise ValueError('One shared native terminal hook slot only')
    # Native lifecycle does not synthesize actor actions or browser navigation.
    return ordinary_factory(site, contract, directory, auth, native_read_hooks=hooks, **kwargs)
