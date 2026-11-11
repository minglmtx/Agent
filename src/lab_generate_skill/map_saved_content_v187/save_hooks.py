"""Passive source-bound hooks for the ordinary terminal-only actor lifecycle."""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urldefrag, urlsplit
import json

from lab_generate_skill.io_utils import atomic_write_json as save
from lab_generate_skill.map_account_initial import observe_account_start
from lab_generate_skill.map_account_readout import session_identity
from lab_generate_skill.map_existing_account_observation import require_anonymous
from lab_generate_skill.map_query_site import IsolatedMapQuerySite
from lab_generate_skill.browser_http_status import is_error_document
from .save_capture import classify, witnessed
from .save_judge import SOURCES, evaluate
from .save_snapshot import capture
from .save_protection import check


class SaveHooks:
    def __init__(self, contract, directory, *, baseline):
        self.kind = next((kind for kind, source in SOURCES.items() if source == contract.get('source_task_id')), None)
        if self.kind is None or contract.get('domain') != 'map':
            raise ValueError('Exact native upload/diary source required')
        self.contract, self.baseline = deepcopy(contract), deepcopy(baseline)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.site = self.context = self.page = self.initial = self.terminal = None
        self.before = self.after = self.trace = None
        self.files_before = self.files_after = None
        self.closed = self.scored = False
        self.step = 0
        self.pending = None
        self.observations, self.issued = [], {}
        self.responses, self.captures, self.errors = [], [], []
        self.inflight, self.documents = {}, {}
        self.events = []

    def prepare(self, site, username):
        if self.site is not None or username is not None or site.domain != 'map' or site.account != self.contract['parameters']['account']:
            raise ValueError('One matching signed-out existing-account site required')
        site.reset_guard.require_unchanged()
        site.require_accounts_unchanged()
        if IsolatedMapQuerySite.fingerprint(site) != self.baseline['native_fingerprint'] or site.fingerprint() != self.baseline['fixture_fingerprint']:
            raise ValueError('Complete original native fixture differs from qualified controls')
        self.before, self.files_before = capture(site, self.directory, 'save-before')
        if self.before['protection']['guard'] != self.baseline['database'] or self.files_before != self.baseline['files']:
            raise ValueError('Original complete native guard differs from qualified controls')
        if self.before['diaries'] or self.before['traces']:
            raise ValueError('Saved target records must not be precreated')
        self.site = site
        self.events.append('prepare')

    def relevant(self, request):
        row = classify(urlsplit(request.url).path)
        return row if row and (row['kind'] == 'reopened' or request.method == 'POST') else None

    def attach(self, context):
        if self.site is None or self.context is not None:
            raise ValueError('One prepared browser context required')
        self.context = context
        for event, callback in [('request', self.started), ('requestfinished', self.finished),
                                ('requestfailed', self.failed), ('response', self.response)]:
            context.on(event, callback)
        self.events.append('attach')

    def response(self, response):
        if response.request.is_navigation_request():
            self.documents[urldefrag(response.url)[0]] = response.status

    def started(self, request):
        if self.relevant(request):
            self.inflight[id(request)] = request.url

    def finished(self, request):
        row = self.relevant(request)
        if row is None:
            return
        self.inflight.pop(id(request), None)
        try:
            actual, origin = urlsplit(request.url), urlsplit(self.site.url)
            if (actual.scheme, actual.netloc) != (origin.scheme, origin.netloc):
                raise ValueError('Foreign native save/readback response')
            response = request.response()
            if response is None:
                raise ValueError('Finished request lacks a native response')
            self.responses.append(dict(row, sequence=len(self.responses), next_observation_step=self.step,
                url=request.url, status=response.status, method=request.method, resource_type=request.resource_type,
                native_response_completed=True, completion_basis='native-requestfinished-event'))
        except Exception as error:
            self.errors.append(type(error).__name__ + ': ' + str(error))

    def failed(self, request):
        if self.relevant(request):
            self.inflight.pop(id(request), None)
            self.errors.append('Native save/readback request failed: ' + str(request.failure))

    def observe_initial(self, page):
        if self.site is None or self.page is not None or page.context is not self.context:
            raise ValueError('One bound original initial page required')
        self.initial = observe_account_start(page, self.contract, self.site.url, self.documents.get(urldefrag(page.url)[0]))
        initial_session = session_identity(self.context, self.site.url)
        require_anonymous(initial_session, self.site.url)
        self.page = page
        self.events.append('observe_initial')
        save(self.directory / 'save-initial.json', dict(original_start=self.initial, session=initial_session))

    def record(self, page):
        if self.closed or self.scored or page.context is not self.context or self.initial is None:
            raise ValueError('Only ordinary current source observations may be recorded')
        step = self.step
        self.step += 1
        self.pending = dict(step=step, url=page.url)
        self.observations.append(dict(self.pending))
        row = classify(urlsplit(page.url).path)
        if row and row['kind'] == 'reopened':
            try:
                responses = [r for r in self.responses if r['kind'] == 'reopened' and r['url'] == page.url and r['method'] == 'GET' and r['resource_type'] == 'document']
                response = responses[-1] if responses else None
                status = response['status'] if response else None
                title = page.title()
                health = dict(url=page.url, title=title, http_status=status,
                    login_page=urlsplit(page.url).path == '/login', error_page=is_error_document(page.url, status, title))
                current = dict(row, step=step, url=page.url, page=health, response=response, capture_error=None)
            except Exception as error:
                message = type(error).__name__ + ': ' + str(error)
                self.errors.append(message)
                current = dict(step=step, capture_error=message)
            self.captures.append(current)
            save(self.directory / f'save-page-{step:03d}.json', current)
        self.events.append('record')

    def acknowledge_issued(self, actual_ax):
        if self.closed or self.pending is None or not isinstance(actual_ax, str):
            raise ValueError('Actual issued current public input required')
        texts = self.issued.setdefault(self.pending['step'], [])
        if actual_ax not in texts:
            texts.append(actual_ax)
        self.events.append('acknowledge_issued')

    def capture_terminal(self, page, terminal):
        if self.closed or self.scored or self.terminal is not None or page.context is not self.context or terminal.get('url') != page.url:
            raise ValueError('One bound terminal document required')
        self.terminal = deepcopy(terminal)
        self.events.append('capture_terminal')

    def close(self):
        if self.closed:
            return
        if self.context is not None:
            for event, callback in [('request', self.started), ('requestfinished', self.finished),
                                    ('requestfailed', self.failed), ('response', self.response)]:
                self.context.remove_listener(event, callback)
        if self.inflight:
            self.errors.append('Native save/readback requests remained incomplete at terminal capture')
        self.closed = True
        self.events.append('close')
        save(self.directory / 'save-index.json', dict(responses=self.responses, captures=self.captures, errors=self.errors))
        save(self.directory / 'save-issued.json', dict(observations=self.observations, issued=self.issued))

    def provide_trace(self, trace):
        if not self.closed or self.trace is not None or not isinstance(trace, dict):
            raise ValueError('One completed ordinary rollout trace required')
        self.trace = deepcopy(trace)
        self.events.append('provide_trace')

    def score_terminal(self, site, terminal, *, runtime_error=None):
        if site is not self.site or not self.closed or self.scored or self.terminal is None or self.terminal != terminal:
            raise ValueError('One score after source context closure required')
        self.scored = True
        self.events.append('score_terminal')
        integrity, protection, witness, error = False, {}, None, None
        try:
            self.after, self.files_after = capture(site, self.directory, 'save-after')
            protection = check(self.kind, self.before['protection'], self.after['protection'], files_before=self.files_before, files_after=self.files_after)
            integrity = protection['passed']
            if not integrity:
                raise ValueError('Complete native save protection failed: ' + protection.get('error', 'unknown'))
            bodies = [dict(goal=self.contract['goal'], url=row['url'], observation='\n'.join(self.issued.get(row['step'], []))) for row in self.observations]
            witness = witnessed(self.kind, self.contract, bodies, dict(responses=self.responses, captures=self.captures, errors=self.errors))
        except Exception as problem:
            error = type(problem).__name__ + ': ' + str(problem)
        judgment = evaluate(self.kind, self.before, self.after, self.contract, witness, terminal, site.url,
                            runtime_error=runtime_error, capture_error=error, trace=self.trace)
        save(self.directory / 'save-terminal.json', dict(events=self.events, kind=self.kind, site_origin=site.url,
            terminal=terminal, witness=witness, protection=protection, integrity=integrity,
            capture_error=error, judgment=judgment, cold_reset_required=True))
        return judgment, integrity
