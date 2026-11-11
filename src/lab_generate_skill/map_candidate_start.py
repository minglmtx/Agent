"""Passive original-start validation; this is not a task success predicate."""
from urllib.parse import urlsplit, parse_qs
from pathlib import Path
from uuid import uuid4

from .map_route import read_route, parse_point, pair_equal, LABELS
from .map_route_initialization_binding import initial_url_state
from .map_view import wait_native_view


def validate_initial(candidate, origin, actual_url, view, route, *, served=None, independent_body=None):
    expected = urlsplit(origin + candidate['start_path'])
    actual = urlsplit(actual_url)
    if ((actual.scheme, actual.netloc, actual.path, actual.query) !=
            (expected.scheme, expected.netloc, expected.path, expected.query)):
        raise ValueError('Original source document/query changed')
    if view.get('map_visible') is not True or not view.get('native_geo_uri'):
        raise ValueError('Native map initial observation missing')
    # Native search and directions fit the view themselves. Plain map starts
    # must retain the declared fragment; wait_native_view also verifies the
    # native (noneditable) map links and coordinate precision.
    if expected.path == '/' and actual.fragment != expected.fragment:
        raise ValueError('Declared plain map initial view changed')
    if parse_qs(expected.query).get('route'):
        pair, mode = initial_url_state(candidate['start_path'])
        hidden_form = (isinstance(route, dict) and route.get('route_form_visible') is False
                       and all(route.get(k) == '' for k in ('origin', 'destination', 'engine')))
        if hidden_form:
            from .map_initial_route_proof import verify_initial_response
            verify_initial_response(candidate['start_path'], route, served, independent_body)
            return True
        if (not isinstance(route, dict) or route.get('route_visible') is not True
                or route.get('loading') is not False or not route.get('rows')
                or route.get('engine') != LABELS[mode]
                or not pair_equal([parse_point(route.get(k)) for k in
                                   ('origin', 'destination')],
                                  [[float(v) for v in p] for p in pair])):
            raise ValueError('Original native route endpoints/mode not rendered')
    return True


class InitialStartHooks:
    """Observe ordinary BrowserGym initialization without clicking or editing."""
    def __init__(self, candidate, site):
        self.candidate, self.site = candidate, site
        self.context = self.initial = self.terminal = None
        self.initial_candidate = None
        self.initial_route_capture = None
        self.events = []

    def attach(self, context):
        if self.context is not None:
            raise ValueError('One private source context required')
        self.context = context
        self.events.append('attach')
        if parse_qs(urlsplit(self.candidate.get('start_path', '')).query).get('route'):
            from .map_route_normal_capture import NativeRouteCapture
            self.initial_route_capture = NativeRouteCapture(context, self.site.route_urls,
                Path(self.site.logs)/('initial-route-'+uuid4().hex))

    def observe_initial(self, page):
        if page.context is not self.context or self.initial is not None:
            raise ValueError('One original initial observation required')
        try:
            view = wait_native_view(page, self.candidate['start_path'])
        except Exception as error:
            # Preserve the already captured readiness signals. A summarized
            # timeout must not discard the facts needed to diagnose a reset.
            self.initial_candidate = dict(url=page.url,
                view=getattr(error, 'last_native_view', None),
                readiness=getattr(error, 'last_native_readiness', None),
                initialization_timeout=True)
            raise
        route = read_route(page) if parse_qs(urlsplit(self.candidate['start_path']).query).get('route') else None
        self.initial_candidate = dict(url=page.url,view=view,route=route)
        served = independent = proof = None
        try:
            if (isinstance(route, dict) and route.get('route_form_visible') is False
                    and all(route.get(k) == '' for k in ('origin', 'destination', 'engine'))):
                from .map_initial_route_proof import read_independent_initial, verify_initial_response
                capture = self.initial_route_capture
                if capture is None or capture.latest_error or not capture.responses:
                    raise ValueError('Hidden initial route lacks actual native response evidence')
                served = capture.responses[-1]
                independent = read_independent_initial(self.site, self.candidate['start_path'])
                proof = verify_initial_response(self.candidate['start_path'], route, served, independent)
                proof['response_directory'] = str(capture.directory)
                self.initial_candidate['initial_route_proof'] = proof
            validate_initial(self.candidate, self.site.url, page.url, view, route,
                             served=served, independent_body=independent)
        finally:
            if self.initial_route_capture is not None:
                self.initial_route_capture.close()
        self.initial = dict(self.initial_candidate)
        self.events.append('observe_initial')

    def record(self, page):
        if page.context is not self.context or self.initial is None:
            raise ValueError('Observation belongs to another source context')

    def capture_terminal(self, page, terminal):
        self.record(page)
        if terminal.get('url') != page.url or self.terminal is not None:
            raise ValueError('One matching final page required')
        self.terminal = dict(terminal)
        self.events.append('capture_terminal')

    def close(self):
        if self.initial_route_capture is not None:
            self.initial_route_capture.close()
        self.events.append('close')
