"""Passive GPS capture using the same ordinary browser lifecycle as providers."""
from copy import deepcopy
import time
from urllib.parse import urlsplit
from .io_utils import atomic_write_json
from .map_provider_observation import ProviderObservationHooks
from .map_provider_contract import validate_resource_family
from .map_gps_overlay_terminal import evaluate

READER = """() => {
  const map = document.querySelector('#map');
  // A healthy document without a visible map is an observed wrong endpoint.
  // A visible map without its state reader remains a capture/runtime failure.
  if (!map || !map.getClientRects().length || map.clientWidth <= 0 || map.clientHeight <= 0)
    return {map_visible: false};
  return typeof window.__labFrozenGPSState === 'function' ? window.__labFrozenGPSState() : null;
}"""


def require_initial_gps(base, gps):
    if (not isinstance(gps,dict) or gps.get('enabled')is not False or gps.get('code')!='G'
            or any(gps.get(k)!=base.get(k)for k in ('zoom','center','size','bounds'))):
        raise ValueError('Disabled native GPS layer at the exact initial map view required')


class GPSObservationHooks(ProviderObservationHooks):
    def __init__(self,candidate,directory,**kwargs):
        validate_resource_family(candidate['candidate_completion'])
        if candidate['candidate_completion']['family']!='gps_overlay':raise ValueError('GPS overlay required')
        super().__init__(candidate,directory,**kwargs)
        self.base_initial=None

    def observe_initial(self,page):
        super().observe_initial(page)
        gps=page.evaluate(READER)
        require_initial_gps(self.initial,gps)
        self.base_initial=self.initial;self.initial=deepcopy(gps)
        atomic_write_json(self.directory/'gps-initial.json',dict(environment_binding=self.binding,
            url=page.url,base_initial=self.base_initial,initial=self.initial,
            reference_phase='native_initial_before_actions',actor_actions=0))

    def capture_terminal(self,page,terminal):
        self._bound_page(page)
        if self.initial is None or self.terminal is not None or terminal.get('url')!=page.url:
            raise ValueError('One actual GPS terminal document required')
        self.terminal=deepcopy(terminal)
        u,expected=urlsplit(page.url),urlsplit(self.site.url);status=terminal.get('http_status')
        valid=(type(status)is int and 200<=status<300 and not terminal.get('login_page')
            and not terminal.get('error_page')and (u.scheme,u.netloc)==(expected.scheme,expected.netloc))
        if valid:
            try:
                self.native_terminal=page.evaluate(READER);until=time.monotonic()+5
                while self.native_terminal and self.native_terminal.get('enabled')is True:
                    tiles=[t for t in self.native_terminal['tiles']if t['current']]
                    pending=any(t['src']not in self.response_errors and
                        (not t['loaded']or t['src']not in self.responses)for t in tiles)
                    if not pending or time.monotonic()>=until:break
                    page.wait_for_timeout(50);self.native_terminal=page.evaluate(READER)
            except Exception as exc:self.capture_error=type(exc).__name__+': '+str(exc)
        self.events.append('capture_terminal')

    def score_terminal(self,site,terminal,*,runtime_error=None):
        if site is not self.site or self.scored or self.terminal is None or terminal!=self.terminal:
            raise ValueError('One bound GPS terminal-only scoring call required')
        self.scored=True;integrity=False
        try:
            site.provider_environment.require_owned();site.reset_guard.require_unchanged()
            integrity=site.fingerprint()==self.baseline and site.native_provider_binding==self.binding
        except Exception:pass
        judgment=evaluate(self.c['candidate_completion'],initial=self.initial,terminal=self.native_terminal,
            page=terminal,site_origin=site.url,server=self.server,response_hashes=self.responses,
            integrity=integrity,runtime_error=runtime_error,capture_error=self.capture_error)
        self.events.append('score_terminal')
        atomic_write_json(self.directory/'gps-terminal.json',dict(events=self.events,baseline=self.baseline,
            environment_binding=self.binding,initial=self.initial,terminal=terminal,native_terminal=self.native_terminal,
            response_sha256=self.responses,integrity=integrity,capture_error=self.capture_error,judgment=judgment))
        return judgment,integrity
