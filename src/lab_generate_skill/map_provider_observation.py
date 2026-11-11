"""Passive lifecycle capture for a worker-owned frozen map-provider profile.

This component does not grant admission. The ordinary dispatch adapter must
supply independently verified environment/baseline evidence before constructing
it. It is also usable by a native lifecycle validator without a model.
"""
from copy import deepcopy
import hashlib
import time
from urllib.parse import urlsplit, parse_qs

from .io_utils import atomic_write_json
from .map_provider_terminal import evaluate_provider_terminal
from .map_route import read_route, parse_point, pair_equal, LABELS
from .map_route_initialization_binding import initial_url_state
from .map_local_capabilities import same_center
from .map_metadata_query import initial_view
from .map_provider_contract import PROVIDER_CODES

READER = "() => typeof window.__labFrozenProviderState==='function' ? window.__labFrozenProviderState() : null"


def require_initial(candidate, state, route, *, initial_document=None):
    if not isinstance(state, dict) or [x['code'] for x in state['active']] != ['M']:
        raise ValueError('Original native Standard layer required')
    initial_url = urlsplit(candidate['start_path'])
    if (candidate['candidate_completion']['retain_initial_route']
            or (initial_url.path == '/directions' and parse_qs(initial_url.query).get('route'))):
        pair, mode = initial_url_state(candidate['start_path'])
        if (not route['route_visible'] or route['loading'] or not route['rows']
                or route['engine'] != LABELS[mode] or not pair_equal(
                    [parse_point(route['origin']), parse_point(route['destination'])],
                    [[float(v) for v in point] for point in pair])):
            raise ValueError('Initial native route differs from the declared start')
    elif urlsplit(candidate['start_path']).path == '/search':
        from .map_candidate_start import validate_initial
        query=parse_qs(urlsplit(candidate['start_path']).query).get('query',[])
        if len(query)!=1 or not query[0].strip() or not isinstance(initial_document,dict):
            raise ValueError('Native search initialization evidence required')
        u=urlsplit(initial_document['url'])
        validate_initial(candidate,u.scheme+'://'+u.netloc,initial_document['url'],
                         initial_document['view'],initial_document.get('route'))
        if not same_center(initial_view('/#'+u.fragment),
                           (state['zoom'],state['center']['lat'],state['center']['lng'])):
            raise ValueError('Provider map differs from actual native search view')
    elif not same_center(initial_view(candidate['start_path']),
                         (state['zoom'], state['center']['lat'], state['center']['lng'])):
        raise ValueError('Initial native area differs from the declared start')


class ProviderObservationHooks:
    """Capture only: no task navigation, actions, private hints or environment edits."""
    def __init__(self, candidate, directory, *, environment_binding, baseline):
        from pathlib import Path
        self.c = deepcopy(candidate)
        self.directory = Path(directory)
        self.binding = deepcopy(environment_binding)
        self.baseline = baseline
        self.site = self.context = self.page = None
        self.initial = self.initial_route = self.terminal = self.native_terminal = None
        self.terminal_route = None
        self.responses = {}
        self.response_errors = set()
        self.events = []
        self.attached = self.scored = False
        self.capture_error = None

    def prepare(self, site, username):
        if self.site is not None or username is not None:
            raise ValueError('One anonymous provider preparation required')
        environment = site.provider_environment
        environment.require_owned()
        if (site.domain != 'map' or site.native_provider_binding != self.binding
                or site.reset_guard is None or not all(getattr(site, k, False) for k in
                    ('with_tiles', 'with_geographic_baseline', 'track_changes'))):
            raise ValueError('Verified full native provider profile required')
        # A same-ID but modified goal/start/provider is not the admitted candidate.
        if self.c not in environment.candidates:
            raise ValueError('Task differs from the worker-owned provider candidates')
        site.reset_guard.require_unchanged()
        if site.fingerprint() != self.baseline:
            raise ValueError('Native provider baseline changed')
        self.site = site
        self.server = environment.server
        self.events.append('prepare')

    def attach(self, context):
        if self.site is None or self.context is not None:
            raise ValueError('One private browser context required')
        self.context = context
        context.on('response', self._response)
        self.attached = True
        self.events.append('attach')

    def _response(self, response):
        if self.scored or not self.attached:
            return
        u, expected = urlsplit(response.url), urlsplit(self.server.url)
        if (u.scheme, u.netloc) != (expected.scheme, expected.netloc) or not u.path.startswith('/tiles/'):
            return
        try:
            if response.status != 200:
                self.responses.pop(response.url, None)
                self.response_errors.add(response.url)
                return
            self.responses[response.url] = hashlib.sha256(response.body()).hexdigest()
            self.response_errors.discard(response.url)
        except Exception:
            self.responses.pop(response.url, None)
            self.response_errors.add(response.url)

    def _bound_page(self, page):
        if self.context is None or page.context is not self.context or self.scored:
            raise ValueError('Only the current private browser page may supply evidence')
        if self.page is not None and page is not self.page:
            raise ValueError('Initial and terminal page handles differ')

    def observe_initial(self, page):
        self._bound_page(page)
        if self.page is not None or not self.attached:
            raise ValueError('Observe the actual initial page exactly once')
        observed, expected = urlsplit(page.url), urlsplit(self.site.url)
        if (observed.scheme, observed.netloc) != (expected.scheme, expected.netloc):
            raise ValueError('Initial provider page is outside the private website')
        page.wait_for_function("() => typeof window.__labFrozenProviderState==='function' && window.__labFrozenProviderState().active.length===1", timeout=15000)
        if self.c['candidate_completion']['retain_initial_route']:
            page.wait_for_function("() => document.querySelectorAll('#sidebar_content tr.turn').length>0 && !jQuery.active", timeout=30000)
        state = page.evaluate(READER)
        route = read_route(page) if self.c['candidate_completion']['retain_initial_route'] else None
        document=None
        if urlsplit(self.c['start_path']).path=='/search':
            from .map_candidate_start import InitialStartHooks
            hook=InitialStartHooks(self.c,self.site);hook.attach(self.context)
            try:
                hook.observe_initial(page);document=hook.initial
                state=page.evaluate(READER)
            finally:hook.close()
        require_initial(self.c, state, route,initial_document=document)
        self.page = page
        self.initial, self.initial_route = deepcopy(state), deepcopy(route)
        atomic_write_json(self.directory/'provider-initial.json', dict(
            environment_binding=self.binding, state=self.initial, route=self.initial_route))
        self.events.append('observe_initial')

    def record(self, page):
        self._bound_page(page)
        if self.initial is None:
            raise ValueError('Initial observation must precede subsequent observations')
        # The ordinary runner already saves AX/action history. Do not duplicate
        # native map snapshots at every step or judge exploratory actions here.

    def capture_terminal(self, page, terminal):
        self._bound_page(page)
        if self.initial is None or self.terminal is not None or terminal.get('url') != page.url:
            raise ValueError('One actual final document required')
        self.terminal = deepcopy(terminal)
        observed, expected = urlsplit(page.url), urlsplit(self.site.url)
        status = terminal.get('http_status')
        valid = (type(status) is int and 200 <= status < 300 and not terminal.get('login_page')
                 and not terminal.get('error_page') and
                 (observed.scheme, observed.netloc) == (expected.scheme, expected.netloc))
        if valid:
            try:
                self.native_terminal = page.evaluate(READER)
                target = PROVIDER_CODES[self.c['candidate_completion']['provider']]
                until = time.monotonic() + 5
                # Wait only for an explicitly selected provider's unfinished
                # images/callbacks. A wrong layer/page requires no extra wait.
                while self.native_terminal and [x['code'] for x in self.native_terminal['active']] == [target]:
                    tiles = [t for t in self.native_terminal['active'][0]['tiles'] if t['current']]
                    pending = any(t['src'] not in self.response_errors and
                        (not t['loaded'] or t['src'] not in self.responses) for t in tiles)
                    if not pending or time.monotonic() >= until:
                        break
                    page.wait_for_timeout(50)
                    self.native_terminal = page.evaluate(READER)
                if self.c['candidate_completion']['retain_initial_route']:
                    self.terminal_route = read_route(page)
            except Exception:
                self.capture_error = 'Native terminal observation unavailable'
        self.events.append('capture_terminal')

    def close(self):
        if self.attached:
            self.context.remove_listener('response', self._response)
            self.attached = False
            self.events.append('close')

    def score_terminal(self, site, terminal, *, runtime_error=None):
        if site is not self.site or self.scored or self.terminal is None or terminal != self.terminal:
            raise ValueError('One bound terminal-only scoring call required')
        self.scored = True
        integrity = False
        try:
            site.provider_environment.require_owned()
            site.reset_guard.require_unchanged()
            integrity = site.fingerprint() == self.baseline and site.native_provider_binding == self.binding
        except Exception:
            pass
        judgment = evaluate_provider_terminal(self.c['candidate_completion'], initial=self.initial,
            terminal=self.native_terminal, page=terminal, site_origin=site.url, server=self.server,
            response_hashes=self.responses, initial_route=self.initial_route, terminal_route=self.terminal_route,
            runtime_error=runtime_error, integrity=integrity, capture_error=self.capture_error)
        self.events.append('score_terminal')
        atomic_write_json(self.directory/'provider-terminal.json', dict(
            events=self.events, environment_binding=self.binding, baseline=self.baseline,
            terminal=terminal, native_terminal=self.native_terminal, terminal_route=self.terminal_route,
            response_sha256=self.responses, integrity=integrity, judgment=judgment))
        return judgment, integrity
