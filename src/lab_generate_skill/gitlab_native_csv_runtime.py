"""Optional native CSV transport bridge, with no browser action policy.

Only a real trusted export-confirmation click and its successful native POST
may authorize claiming a newly observed native JID. The installed worker,
finder, export service and CSV builder remain unchanged. A bounded local MIME
transport replaces external email; queued requests are never completion.
Private records, queue payloads and expected answers never enter model input.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, unquote, urlsplit

from . import gitlab_native_csv_admission as admission
from . import gitlab_native_csv_probe as native
from .gitlab_native_csv_delivery import public_attachment_metadata

VERSION = 'gitlab-native-csv-runtime-v1'
MAX_EXPORTS = 6


def enabled(contract):
    return contract.get('domain') == 'gitlab' and isinstance(contract.get('native_csv_export'), dict)


def owned_transport(parent, site, contract):
    """Get the already prepared transport; the parent retains terminal scoring."""
    # The registered frozen adapter removes only its private admission pointer
    # before constructing the parent. Compare that same verified definition,
    # not the runner's transport envelope (and never ignore arbitrary fields).
    from . import native_goal_dispatch
    implementation = native_goal_dispatch.protocol(contract)
    if getattr(implementation, 'OWNS_NATIVE_CSV_TRANSPORT', False) is True:
        canonical = getattr(implementation, 'canonical', None)
        if not callable(canonical):
            raise ValueError('CSV lifecycle owner must expose its contract binding')
        contract = canonical(contract)
    child = getattr(parent, 'csv', None)
    if (not isinstance(child, NativeCsvHooks) or not getattr(parent, 'prepared', False)
            or not child.prepared or child.site is not site or getattr(parent, 'site', None) is not site
            or child.contract != contract or parent.contract != contract):
        raise ValueError('CSV transport must be prepared by this exact native lifecycle')
    return child


def _load_bound(path, sha):
    p = Path(path)
    if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.stat().st_size > 32000000:
        raise ValueError('Exact immutable private CSV evidence file required')
    payload = p.read_bytes()
    if not isinstance(sha, str) or hashlib.sha256(payload).hexdigest() != sha:
        raise ValueError('Private native CSV evidence bytes changed')
    return json.loads(payload)


def inputs(contract):
    if not enabled(contract) or contract.get('heldout_quarantine') is not False or contract.get('eligible_for_training') is not False:
        raise ValueError('Explicit development native CSV contract required')
    spec = contract['native_csv_export']
    if spec.get('version') != VERSION or type(spec.get('consumer_seconds')) is not int or not 1 <= spec['consumer_seconds'] <= 300:
        raise ValueError('Versioned, bounded native CSV runtime required')
    case = _load_bound(spec['case_file'], spec['case_sha256'])
    baseline = _load_bound(spec['baseline_file'], spec['baseline_sha256'])
    admission.full_snapshot(baseline)
    for field in ('source_task_id', 'goal', 'start_path', 'recorded_start_paths', 'source_trace_ids'):
        if contract.get(field) != case.get(field):
            raise ValueError('CSV contract differs from original or explicitly versioned task binding')
    if contract.get('start_path') != contract['recorded_start_paths'][0]:
        raise ValueError('Original first start must be preserved')
    return case, baseline


def require_admission(contract, proof):
    case, baseline = inputs(contract)
    if proof.get('version')=='gitlab-native-csv-bridge-normal-controls-v1'and proof.get('formal_runtime_preinference_gates_validated')is not True:
        raise ValueError('Actual complete native runtime factory lifecycle proof required')
    formal_sources=proof.get('formal_runtime_preinference_gate_sources')
    if formal_sources is not None and (not isinstance(formal_sources,list) or not formal_sources or not all(isinstance(v,str) for v in formal_sources) or len(set(formal_sources))!=len(formal_sources) or case['source_task_id']not in formal_sources):
        raise ValueError('Actual merged runtime evidence does not cover this source')
    # The unqualified original MR never inherits an Open-only gate. A distinct
    # All revision needs its own full normal proof before this branch is used.
    return admission.require_scope_controls(case, proof, native_baseline=baseline)


def require_original_binding(contract, original_contract, source):
    case, _ = inputs(contract)
    if {k:v for k,v in contract.items() if k!='admission_result'} != original_contract:
        raise ValueError('CSV normal binding changed after controls')
    if (source.get('task_id')!=contract.get('source_task_id') or source.get('domain')!='gitlab' or
            source.get('goal')!=case.get('original_goal',case['goal']) or
            source.get('heldout_quarantine') is not False or
            source.get('source_trace_ids')!=contract.get('source_trace_ids')):
        raise ValueError('CSV original inventory source/goal/aliases differ')
    def path(url):
        value=urlsplit(url)
        return value.path+('?' + value.query if value.query else '')+('#'+value.fragment if value.fragment else '')
    if [path(v) for v in source['recorded_start_urls']]!=contract.get('recorded_start_paths'):
        raise ValueError('CSV original first and recorded starts differ')


def _origin(value):
    p = urlsplit(value)
    if (p.scheme not in ('http', 'https') or not p.hostname or p.username is not None
            or p.password is not None or p.path not in ('', '/') or p.query or p.fragment):
        raise ValueError('Trusted site factory origin required')
    p.port
    return p.scheme, p.netloc


def _export_request(value, site_origin):
    p = urlsplit(value)
    if (p.scheme, p.netloc) != _origin(site_origin) or p.username is not None or p.password is not None or p.fragment:
        raise ValueError('Actual local native confirmation URL required')
    match = re.fullmatch(r'/([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)/-/(issues|merge_requests)/export_csv', unquote(p.path))
    if not match:
        raise ValueError('Actual native project collection export path required')
    # Native export links inherit request.query_parameters. Installed MR lists
    # explicitly include scope=all: the unfiltered current-project collection,
    # not an assignee/author/search filter. Accept it only with one legal state;
    # preserve empty/state-only queries and reject every other scope/filter.
    state = None
    if p.query:
        try:
            pairs = parse_qsl(p.query, keep_blank_values=True,
                              strict_parsing=True, max_num_fields=2)
        except ValueError:
            raise ValueError('Unsupported native confirmation scope query') from None
        allowed = {'opened', 'closed', 'all'}
        if match[2] == 'merge_requests':
            allowed.add('merged')
        params = dict(pairs)
        if (len(params) != len(pairs) or params.get('state') not in allowed or
                set(params) not in ({'state'}, {'scope', 'state'}) or
                ('scope' in params and
                 (match[2] != 'merge_requests' or params['scope'] != 'all'))):
            raise ValueError('Unsupported native confirmation scope query')
        state = params['state']
    return p.path, match[1], match[2], state


def _export_path(value, site_origin):
    return _export_request(value, site_origin)[:3]


# Passive public listener. No navigation, forced click, extra HTTP request,
# event alteration, hidden expected value or task-specific strategy.
PASSIVE_CLICK = r'''(() => {
 document.addEventListener('click', event => {
  const a=event.target.closest('a[href]'); if(!a)return;
  const href=new URL(a.href,location.href);
  if(!/\/-\/(issues|merge_requests)\/export_csv$/.test(href.pathname))return;
  const shown=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
  const modal=a.closest('.modal,[role=dialog]');
  const tabs=[...document.querySelectorAll('.nav-link.active,[role=tab][aria-selected=true]')].filter(shown).map(e=>e.innerText.trim());
  const ids=[...new Set([...document.querySelectorAll('[data-project-id]')].map(e=>e.getAttribute('data-project-id')))];
  window.__labNativeCsvPublicClick({trusted:event.isTrusted,url:href.href,page_url:location.href,
    label:a.innerText.trim(),project_ids:ids,active_tabs:tabs,
    visible_confirmation:!!modal&&shown(modal)&&shown(a)});
 },true);
})();'''


def validate_activation(value, *, site_origin):
    if not isinstance(value, dict) or value.get('trusted') is not True or value.get('visible_confirmation') is not True:
        raise ValueError('Real trusted visible native confirmation required')
    path, project_path, collection, request_state = _export_request(value.get('url', ''), site_origin)
    current = urlsplit(value.get('page_url', ''))
    if (current.scheme, current.netloc) != _origin(site_origin) or unquote(current.path) != path[:-len('/export_csv')]:
        raise ValueError('Confirmation belongs to another current native collection page')
    ids = value.get('project_ids')
    if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str) or not re.fullmatch('[1-9][0-9]*', ids[0]):
        raise ValueError('One observed public project identity required')
    tabs = value.get('active_tabs')
    labels = {'open': 'opened', 'closed': 'closed', 'merged': 'merged', 'all': 'all'}
    states = [labels[m.group(1).lower()] for tab in tabs if isinstance(tab, str)
              for m in [re.fullmatch(r'(Open|Closed|Merged|All)\s+[0-9][0-9,]*', tab, re.I)] if m] if isinstance(tabs, list) else []
    if len(states) != 1:
        raise ValueError('Actual native active collection filter is not observable')
    if request_state is not None and request_state != states[0]:
        raise ValueError('Native confirmation query differs from observed active state')
    label = 'Export issues' if collection == 'issues' else 'Export merge requests'
    if value.get('label') != label:
        raise ValueError('Observed native export-confirmation label differs')
    observed = {'path': path, 'project_path': project_path, 'project_id': int(ids[0]),
                'kind': 'issue' if collection == 'issues' else 'merge_request', 'state': states[0]}
    if request_state is not None:
        observed['request_state'] = request_state
    return observed


def _safe_exception(error):
    # Never persist arbitrary browser/SQL stderr, page text or queue payload.
    record = {'exception_type': type(error).__name__, 'raw_values_not_saved': True}
    known = {
        'Actual local native confirmation URL required': 'confirmation_origin',
        'Actual native project collection export path required': 'confirmation_path',
        'Unsupported native confirmation scope query': 'confirmation_scope_query',
        'Native confirmation query differs from observed active state': 'confirmation_state_mismatch',
        'Native confirmation response scope differs from its trusted activation': 'response_state_mismatch',
        'Native activation did not come from the bound browser context': 'activation_context',
        'Native activation did not come from the actual main document': 'activation_frame',
        'Native confirmation response did not come from the actual main document': 'response_frame',
        'Native confirmation response came from another browser context': 'response_context',
        'One observed native activation and response per actual browser action required': 'activation_response_count',
        'Native confirmation response does not belong to its trusted activation page': 'response_page',
        'Native confirmation did not produce its matching successful POST': 'response_post',
    }
    if type(error) is ValueError and str(error) in known:
        record['protocol_reason'] = known[str(error)]
    return record


def prepared_parent_snapshot(parent, transport, site):
    """Consume the immediately preceding common prepare's complete snapshot.

    CPU controls compose common state protection and CSV transport in the same
    call stack. This does not accept a saved result, a prior control's capture,
    or a snapshot taken before the current reset. Ordinary CSV preparation
    continues to read its own fresh snapshot.
    """
    if (parent.site is not site or parent.csv is not transport
            or parent.prepared is not True or parent.context is not None
            or parent.events != ['prepare']
            or parent.prepare_generation != site.generation
            or parent.contract != transport.contract
            or Path(parent.directory).resolve() != Path(transport.directory).resolve()
            or transport.prepared or getattr(transport, '_parent_snapshot_consumed', False)):
        raise ValueError('Immediate same-control native preparation required')
    from .gitlab_native_read_runtime import full_snapshot
    full_snapshot(parent.before)
    transport._parent_snapshot_consumed = True
    return deepcopy(parent.before)


class NativeCsvHooks:
    """A source-local passive transport lifecycle; reward is terminal-only."""
    def __init__(self, contract, proof, directory):
        self.contract, self.proof = deepcopy(contract), deepcopy(proof)
        self.directory = Path(directory)
        self.site = None; self.context = None; self.gate = None
        self.activations = []; self.responses = []; self.received = []
        self.activation_pages = []; self.response_pages = []
        self.before_action_queues = None; self.claimed = []
        self.queue_initial = None; self.native_initial = None; self.account = None; self.pending = []; self.consumed = False
        self.faults = []; self.prepared = False; self.username = None; self.event_index = 0; self.scored = False

    def prepare(self, site, username):
        if self.prepared:
            raise ValueError('One native CSV prepare per original reset required')
        from .gitlab_native_csv_probe import protected_snapshot_session, auth_backup, queue_snapshot
        _origin(site.url)
        self.site = site; self.username = username
        self.native_initial = protected_snapshot_session(site, self.directory/'csv-protected-progress.jsonl')
        case, _ = inputs(self.contract)
        self.gate = admission.require_scope_controls(case, self.proof, native_baseline=self.native_initial)
        paths=sorted(self.gate['native_chain'])
        base='/opt/gitlab/embedded/service/gitlab-rails/'
        output=site.command(['sha256sum',*[base+path for path in paths]],capture_output=True,text=True,timeout=40).stdout
        chain={}
        for line in output.splitlines():
            parts=line.split(maxsplit=1)
            if len(parts)!=2 or not re.fullmatch('[0-9a-f]{64}',parts[0]) or not parts[1].strip().startswith(base):
                raise ValueError('Complete native export chain fingerprint unavailable')
            key=parts[1].strip()[len(base):]
            if key in chain:raise ValueError('Duplicate native export chain source')
            chain[key]=parts[0]
        if chain!=self.gate['native_chain']:raise ValueError('Installed native export chain differs from CPU controls')
        native.private_json(self.directory/'csv-installed-chain.json',chain)
        self.account = auth_backup(site, username)
        if self.account['id'] != self.gate['private_reference']['user_id']:
            raise ValueError('Actual factory account differs from native control proof')
        config = (site.state/'data/gitlab-rails/etc/gitlab.yml').read_text()
        if not re.search(r'^\s*email_enabled:\s*false\s*$', config, re.M):
            raise ValueError('Only explicitly disabled external email may use local transport')
        self.queue_initial = queue_snapshot(site, self.directory/'csv-queue-progress.jsonl')
        native.private_json(self.directory/'csv-native-before.json', self.native_initial)
        self.prepared = True

    def attach(self, context):
        if not self.prepared or self.context is not None:
            raise ValueError('Prepared source-local native CSV collector required')
        self.context = context
        context.expose_binding('__labNativeCsvPublicClick', self._click)
        context.add_init_script(PASSIVE_CLICK)
        context.on('response', self._response)

    def _click(self, source, value):
        try:
            observed = validate_activation(value, site_origin=self.site.url)
            page = source.get('page')
            if page is None or page.context is not self.context:
                raise ValueError('Native activation did not come from the bound browser context')
            if source.get('frame')is not page.main_frame:
                raise ValueError('Native activation did not come from the actual main document')
            self.activations.append(observed)
            self.activation_pages.append(page)
        except Exception as error:
            self.faults.append({'stage': 'public_activation', **_safe_exception(error)})

    def _response(self, response):
        try:
            p = urlsplit(response.url)
            if (p.scheme, p.netloc) != _origin(self.site.url) or not p.path.endswith('/export_csv'):
                return
            path, _, _, request_state = _export_request(response.url, self.site.url)
            frame=response.request.frame;page=frame.page
            if frame is not page.main_frame:
                raise ValueError('Native confirmation response did not come from the actual main document')
            if page.context is not self.context:
                raise ValueError('Native confirmation response came from another browser context')
            observed = {'path': path, 'method': response.request.method, 'status': response.status}
            if request_state is not None:
                observed['request_state'] = request_state
            self.responses.append(observed)
            self.response_pages.append(page)
        except Exception as error:
            self.faults.append({'stage': 'native_response', **_safe_exception(error)})

    def before_action(self, page):
        if not self.prepared:
            raise ValueError('Native CSV factory checks must precede actor inference')
        self.activations.clear(); self.responses.clear()
        self.activation_pages.clear(); self.response_pages.clear()
        self.before_action_queues = native.queue_snapshot(self.site, self.directory/'csv-queue-progress.jsonl')

    def after_action(self, page):
        if not self.activations and not self.responses:
            return
        try:
            if self.before_action_queues is None or len(self.activations) != 1 or len(self.responses) != 1:
                raise ValueError('One observed native activation and response per actual browser action required')
            if len(self.activation_pages)!=1 or len(self.response_pages)!=1 or self.activation_pages[0]is not self.response_pages[0]:
                raise ValueError('Native confirmation response does not belong to its trusted activation page')
            observed, response = self.activations[0], self.responses[0]
            if response['path'] != observed['path'] or response['method'] != 'POST' or response['status'] not in (200,302,303):
                raise ValueError('Native confirmation did not produce its matching successful POST')
            if response.get('request_state') != observed.get('request_state'):
                raise ValueError('Native confirmation response scope differs from its trusted activation')
            if len(self.claimed) >= MAX_EXPORTS:
                raise ValueError('Native source export budget exhausted')
            after = native.queue_snapshot(self.site, self.directory/'csv-queue-progress.jsonl')
            native.private_json(self.directory/f'csv-discovery-{len(self.claimed)}.json', native.native_export_discovery_capture(self.before_action_queues, after))
            record = native.new_export_job(self.before_action_queues, after, kind=observed['kind'],
                user_id=self.account['id'], project_id=observed['project_id'], state=observed['state'])
            jid = record['job']['jid']
            if jid in self.claimed:
                raise ValueError('Native JID has already been consumed')
            claim = native.claim_job(self.site, record)
            self.claimed.append(jid)
            self.pending.append({'job':record['job'],'claim':claim,'observed':observed})
            native.private_json(self.directory/f'csv-claimed-{len(self.claimed):02d}.json',{'job_id':jid,'raw_sha256':claim['raw_sha256'],'observed':observed,'actual_native_claim':True,'not_completion':True})
        except Exception as error:
            self.faults.append({'stage':'native_transport', **_safe_exception(error)})
            native.private_json(self.directory/f'csv-transport-diagnostics-{self.event_index:02d}.json', self.faults)
        finally:
            self.activations.clear(); self.responses.clear(); self.before_action_queues = None; self.event_index += 1
            self.activation_pages.clear();self.response_pages.clear()

    def consume_terminal(self):
        # Complete only genuinely requested exports, after browser rollout.
        # No request is manufactured and no public observation is augmented
        # with expected data. One native Rails start can process this bounded
        # source's unchanged bundle rather than restarting for every export.
        if self.consumed:
            raise ValueError('One native worker bundle per terminal source required')
        self.consumed=True
        if not self.pending:
            return
        try:
            dest=self.directory/'csv-consumer-terminal';dest.mkdir(mode=0o700)
            from probe_gitlab_native_csv_controls import run_consumer,read_delivery
            jobs=[{'job':item['job'],'claim':item['claim']}for item in self.pending]
            saved,results,failure=run_consumer(self.site,jobs,dest,self.contract['native_csv_export']['consumer_seconds'],
                native_directory='csv-private-'+self.claimed[0])
            if failure is not None:raise ValueError('Bounded native worker failed')
            for pending in self.pending:
                jid=pending['job']['jid'];value=results.get(jid);observed=pending['observed']
                if not isinstance(value,dict)or value.get('stage')!='complete'or value.get('reference_unchanged')is not True:
                    raise ValueError('Claimed native worker/reference did not complete unchanged')
                item=read_delivery(saved,jid);context=item['native_context']
                if (context['user_id']!=self.account['id']or context['project_id']!=observed['project_id']or
                    context['project_path']!=observed['project_path']or context['type']!=observed['kind']):
                    raise ValueError('Actual MIME identity differs from observed native activation/JID')
                self.received.append(item)
            native.private_json(self.directory/'csv-received-private.json',self.received)
            native.private_json(self.directory/'csv-local-artifact-public.json',[public_attachment_metadata(item)for item in self.received])
        except Exception as error:
            self.faults.append({'stage':'native_terminal_transport',**_safe_exception(error)})
            native.private_json(self.directory/'csv-terminal-transport-diagnostics.json',self.faults)

    def score_terminal(self, page, *, runtime_error=False):
        if not self.prepared or self.scored:
            raise ValueError('Exactly one prepared terminal native CSV score required')
        self.scored = True
        if not self.consumed:self.consume_terminal()
        integrity = {'native_full_state_preserved': False, 'native_prior_queues_preserved': False,
                     'bound_auth_metadata_restored': False, 'claimed_native_jids': list(self.claimed)}
        try:
            native.restore_auth_metadata(self.site, self.account)
            integrity['bound_auth_metadata_restored'] = native.auth_backup(self.site, self.username) == self.account
            after = native.protected_snapshot_session(self.site, self.directory/'csv-protected-progress.jsonl')
            queues = native.queue_snapshot(self.site, self.directory/'csv-queue-progress.jsonl')
            integrity['native_full_state_preserved'] = after == self.native_initial
            integrity['native_prior_queues_preserved'] = native.existing_jobs_preserved(self.queue_initial, queues, self.claimed)
            native.private_json(self.directory/'csv-native-after.json', after)
        except Exception as error:
            self.faults.append({'stage':'native_terminal_protection', **_safe_exception(error)})
        native.private_json(self.directory/'csv-integrity.json', integrity)
        healthy = (isinstance(page,dict) and type(page.get('http_status'))is int and
                   200 <= page['http_status'] < 300 and
                   (urlsplit(page.get('url','')).scheme,urlsplit(page.get('url','')).netloc)==_origin(self.site.url) and
                   page.get('login_page') is False and page.get('error_page') is False)
        if not isinstance(page,dict) or type(page.get('http_status'))is not int:
            runtime_error = True
        judgments = [admission.score_received(self.gate, item, site_origin=self.site.url, page_valid=healthy,
                        runtime_error=bool(runtime_error or self.faults),
                        complete_state_preserved=all(integrity[k] for k in ('native_full_state_preserved','bound_auth_metadata_restored')),
                        complete_prior_queue_preserved=integrity['native_prior_queues_preserved'])
                     for item in self.received or [None]]
        # Multiple real exports are permitted; an earlier wrong-object trial
        # is not a terminal failure if a later complete correct export exists.
        judgment = next((j for j in reversed(judgments) if j['status']=='success'), judgments[-1])
        return judgment, integrity

    def close(self):
        if self.context is not None:
            try:self.context.remove_listener('response', self._response)
            except Exception:pass
            self.context = None


feedback = admission.terminal_feedback
