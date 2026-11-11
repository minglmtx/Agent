"""Passive ordinary observation and terminal hooks for native diary/RSS reads."""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urldefrag
import json

from lab_generate_skill.io_utils import atomic_write_json as save
from lab_generate_skill.map_account_initial import observe_account_start
from lab_generate_skill.map_account_readout import session_identity
from lab_generate_skill.map_existing_account_observation import require_anonymous
from lab_generate_skill.map_query_site import IsolatedMapQuerySite
from lab_generate_skill.map_reset_guard import STATE_SQL, checked_state, persistent_files
from .rss_client import evaluate as evaluate_rss, VERSION as RSS_VERSION
from .diary_read import evaluate as evaluate_ny, READ as NY_READ, VERSION as NY_VERSION
from .profile import declared_profile

RSS_READ = r'''() => {const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=="hidden";return {url:location.href,ids:[...document.querySelectorAll('li[data-subscription-id]')].filter(visible).map(e=>e.dataset.subscriptionId)};}'''
SOURCES = {'cb16efd063fc41a3f9d5': 'rss', '40cd6ea96d1b834eddfc': 'ny'}


def native_guard(site):
    value = dict(database=checked_state(json.loads(site.app_sql(STATE_SQL))),
                 files=persistent_files(site.state / 'frontend/app'), baseline=site.geographic_baseline,
                 native_fingerprint=IsolatedMapQuerySite.fingerprint(site), fixture_fingerprint=site.fingerprint(),
                 diaries=site.diary_records())
    return json.loads(json.dumps(value))


class ReaderHooks:
    def __init__(self, contract, directory, *, baseline):
        self.kind = SOURCES.get(contract.get('source_task_id'))
        if self.kind is None or contract.get('domain') != 'map':
            raise ValueError('Exact qualified reader/diary source required')
        self.contract, self.baseline = deepcopy(contract), deepcopy(baseline)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.site = self.context = self.initial = self.terminal = self.pending = None
        self.closed = self.scored = False
        self.documents = {}
        self.captures, self.observations, self.events = [], [], []

    def prepare(self, site, username):
        fixture = declared_profile()
        if self.site is not None or username is not None or site.domain != 'map' or site.account != fixture['account'] or site.diaries != fixture['diaries']:
            raise ValueError('One matching original native reader/diary fixture required')
        site.reset_guard.require_unchanged()
        site.require_accounts_unchanged()
        current = dict(native=native_guard(site), reader=site.reader_snapshot())
        if current != self.baseline or current['reader']['logical']['records']:
            raise ValueError('Complete native and empty reader baseline differs')
        self.site, self.before = site, current
        self.event_start = len(site.reader.events)
        self.private = dict(entries=[])
        for spec in fixture['diaries']:
            rows = [row for row in current['native']['diaries'] if all(row[k] == spec[k] for k in ('title', 'body', 'latitude', 'longitude'))]
            if len(rows) != 1 or rows[0]['visible'] is not True or rows[0]['author'] != fixture['account']['display_name']:
                raise ValueError('Native synthetic diary fixture identity differs')
            if spec['region'] == 'New York City':
                self.private['entries'].append(dict(rows[0], region=spec['region']))
        save(self.directory / 'reader-native-before.json', current)
        save(self.directory / 'native-diary-reference.json', self.private)
        self.events.append('prepare')

    def attach(self, context):
        if self.site is None or self.context is not None:
            raise ValueError('One prepared source browser context required')
        self.context = context
        context.on('response', self.response)
        self.events.append('attach')

    def response(self, response):
        if response.request.is_navigation_request():
            self.documents[urldefrag(response.url)[0]] = response.status

    def observe_initial(self, page):
        if self.initial is not None or page.context is not self.context:
            raise ValueError('One original source start required')
        self.initial = observe_account_start(page, self.contract, self.site.url, self.documents.get(urldefrag(page.url)[0]))
        initial_session = session_identity(self.context, self.site.url)
        require_anonymous(initial_session, self.site.url)
        save(self.directory / 'reader-initial.json', dict(original_start=self.initial, session=initial_session))
        self.events.append('observe_initial')

    def record(self, page):
        if self.closed or self.scored or self.initial is None or page.context is not self.context:
            raise ValueError('One current bound ordinary observation required')
        state = page.evaluate(RSS_READ if self.kind == 'rss' else NY_READ)
        if state['url'] != page.url:
            raise ValueError('Public capture belongs to a stale document')
        self.pending = dict(step=len(self.captures), state=state)
        self.captures.append(deepcopy(self.pending))
        save(self.directory / f'reader-capture-{self.pending["step"]:03d}.json', self.pending)
        self.events.append('record')

    def acknowledge_issued(self, actual_ax):
        if self.closed or self.pending is None or not isinstance(actual_ax, str):
            raise ValueError('Actual post-budget ordinary public input required')
        value = dict(self.pending['state'], step=self.pending['step'], actual_public_text=actual_ax)
        if not self.observations or self.observations[-1] != value:
            self.observations.append(value)
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
            self.context.remove_listener('response', self.response)
        self.closed = True
        self.events.append('close')
        save(self.directory / 'reader-issued.json', dict(captures=self.captures, observations=self.observations))

    def provide_trace(self, trace):
        if not self.closed or hasattr(self, 'trace') or not isinstance(trace, dict):
            raise ValueError('One completed ordinary trace required')
        self.trace = deepcopy(trace)
        self.events.append('provide_trace')

    def score_terminal(self, site, terminal, *, runtime_error=None):
        if site is not self.site or not self.closed or self.scored or self.terminal is None or terminal != self.terminal:
            raise ValueError('One terminal-only score after context closure required')
        self.scored = True
        self.events.append('score_terminal')
        after, integrity, reopened = None, False, None
        native_events = deepcopy(site.reader.events[self.event_start:])
        try:
            after = dict(native=native_guard(site), reader=site.reader_snapshot())
            integrity = after['native'] == self.before['native']
            if not integrity:
                raise ValueError('Complete native Map state changed')
            if self.kind == 'ny':
                if after['reader'] != self.before['reader']:
                    integrity = False
                    raise ValueError('Read-only diary task changed the local reader')
                judgment = evaluate_ny(self.private, self.observations, terminal, origin=site.url,
                                       native_unchanged=True, runtime_error=runtime_error)
            else:
                responses = [dict({k: v for k, v in row.items() if k != 'body_hex'}, body=bytes.fromhex(row['body_hex']))
                             for event in native_events for row in event.get('responses', [])]
                matching = [row for row in self.observations if row['url'] == terminal['url']]
                observed = matching[-1] if matching else dict(ids=[], actual_public_text='')
                reopened = dict(url=terminal['url'], http_status=terminal['http_status'], error=terminal['error_page'],
                    method='GET' if any(event['event'] == 'reader_reopened' for event in native_events) else None,
                    visible_subscription_ids=observed['ids'], actual_public_text=observed['actual_public_text'])
                judgment = evaluate_rss(self.before['reader']['logical'], after['reader']['logical'], origin=site.url,
                    responses=responses, reopened=reopened, runtime_error=runtime_error,
                    request_events=native_events, trace=self.trace, contract=self.contract)
        except Exception as error:
            judgment = dict(version=RSS_VERSION if self.kind == 'rss' else NY_VERSION, status='unknown',
                            reward=None, reason=type(error).__name__ + ': ' + str(error))
        save(self.directory / 'reader-native-after.json', after)
        save(self.directory / 'reader-events.json', native_events)
        save(self.directory / 'reader-terminal.json', dict(events=self.events, site_origin=site.url,
            terminal=terminal, integrity=integrity, reopened=reopened, judgment=judgment))
        return judgment, integrity
