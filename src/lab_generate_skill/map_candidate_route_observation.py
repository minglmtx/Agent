"""Passive ordinary-runner hooks for independently validated route tasks."""
from copy import deepcopy
from pathlib import Path
import time
from urllib.parse import urlsplit

from .io_utils import atomic_write_json
from .map_candidate_start import InitialStartHooks
from .map_candidate_route_terminal import evaluate_terminal
from .map_route import read_route
from .map_route_normal_capture import NativeRouteCapture


class RouteObservationHooks(InitialStartHooks):
    def __init__(self, candidate, directory, *, baseline, references):
        if candidate.get('candidate_completion',{}).get('family')!='displayed_route':
            raise ValueError('Explicit displayed-route task required')
        super().__init__(deepcopy(candidate),None)
        self.directory=Path(directory)
        self.baseline=baseline
        self.references=deepcopy(references)
        self.capture=self.page=self.native_terminal=self.served=None
        self.capture_error=None
        self.scored=False
        self.closed=False

    def prepare(self, site, username):
        if self.site is not None or username is not None or site.domain!='map':
            raise ValueError('One anonymous native Map preparation required')
        if not self.baseline or not all(getattr(site,k,False) for k in ('with_tiles','with_geographic_baseline','track_changes')):
            raise ValueError('Verified full geographic environment required')
        site.reset_guard.require_unchanged()
        if site.fingerprint()!=self.baseline:
            raise ValueError('Validated route baseline changed')
        self.site=site
        self.events.append('prepare')

    def attach(self, context):
        if self.site is None:
            raise ValueError('Prepare before browser capture')
        super().attach(context)
        self.capture=NativeRouteCapture(context,self.site.route_urls,self.directory/'native-route-responses')

    def observe_initial(self,page):
        if self.page is not None:
            raise ValueError('One initial route document required')
        super().observe_initial(page)
        self.page=page
        atomic_write_json(self.directory/'route-initial.json',self.initial)

    def capture_terminal(self,page,terminal):
        if page is not self.page or self.closed or self.scored:
            raise ValueError('Bound actor page required')
        super().capture_terminal(page,terminal)
        actual,expected=urlsplit(page.url),urlsplit(self.site.url)
        valid=(type(terminal.get('http_status'))is int and 200<=terminal['http_status']<300
               and not terminal.get('login_page') and not terminal.get('error_page')
               and (actual.scheme,actual.netloc)==(expected.scheme,expected.netloc))
        if valid:
            try:
                self.native_terminal=read_route(page)
                until=time.monotonic()+5
                # Only unfinished routing/callbacks warrant a short wait; no
                # clicks, navigation, coordinate rewriting or fresh reference.
                while self.native_terminal['loading'] or (self.native_terminal['route_visible']
                        and not self.capture.responses and self.capture.latest_error is None):
                    if time.monotonic()>=until:break
                    page.wait_for_timeout(50)
                    self.native_terminal=read_route(page)
            except Exception as exc:
                self.capture_error=type(exc).__name__+': native terminal capture unavailable'
        self.served=deepcopy(self.capture.responses[-1]) if self.capture.responses else None
        if self.capture.latest_error:
            self.capture_error='Latest native response capture failed'

    def close(self):
        if self.closed:return
        if self.capture is not None:self.capture.close()
        super().close()
        self.closed=True

    def score_terminal(self,site,terminal,*,runtime_error=None):
        if site is not self.site or self.scored or self.terminal is None or self.terminal!=terminal:
            raise ValueError('One bound terminal-only judgment required')
        self.scored=True
        try:
            site.reset_guard.require_unchanged()
            integrity=site.fingerprint()==self.baseline
        except Exception:
            integrity=False
        judgment=evaluate_terminal(self.references,page=terminal,state=self.native_terminal,
            served=self.served,site_origin=site.url,runtime_error=runtime_error,
            capture_error=self.capture_error,integrity=integrity)
        self.events.append('score_terminal')
        atomic_write_json(self.directory/'route-terminal.json',dict(events=self.events,
            baseline=self.baseline,terminal=terminal,native_terminal=self.native_terminal,
            served_response_index=self.served.get('response_index') if self.served else None,
            capture_error=self.capture_error,integrity=integrity,judgment=judgment))
        return judgment,integrity
