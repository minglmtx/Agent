"""Passive combined provider/export lifecycle for native control validation.

An actor dispatcher must separately require a reviewed composition proof before
constructing this hook. No ordinary download admission is accepted here.
"""
from copy import deepcopy
from urllib.parse import urlsplit

from . import map_export_normal as normal
from . import map_ordered_export as ordered
from . import map_osm_artifact as artifact
from .browser_http_status import terminal_document_evidence, is_error_document
from .io_utils import atomic_write_json as save
from .map_candidate_start import InitialStartHooks
from .map_export_transport import NativeExportTransport
from .map_provider_observation import ProviderObservationHooks, READER


class OrderedExportHooks(ProviderObservationHooks):
    def __init__(self, candidate, directory, *, environment_binding, baseline):
        ordered.validate(candidate)
        super().__init__(candidate, directory, environment_binding=environment_binding, baseline=baseline)
        self.start = self.transport = None
        self.initial_export = self.current_export = self.reference = None

    def prepare(self, site, username):
        super().prepare(site, username)
        from probe_map_export_normal import native_reference
        self.reference = native_reference(site, self.directory)
        self.start = InitialStartHooks(self.c, site)

    def attach(self, context):
        super().attach(context)
        self.start.attach(context)
        self.transport = NativeExportTransport(context, self.site.url)

    def observe_initial(self, page):
        self._bound_page(page)
        if self.initial is not None:
            raise ValueError('One initial observation required')
        self.start.observe_initial(page)
        page.wait_for_function("() => typeof window.__labFrozenProviderState==='function'", timeout=15000)
        state = page.evaluate(READER)
        if not isinstance(state, dict) or [x.get('code') for x in state.get('active', [])] != ['M']:
            raise ValueError('Original Standard layer required before actor actions')
        self.initial = deepcopy(state)
        self.page = page
        self.initial_export = self.record(page)
        save(self.directory/'ordered-export-initial.json', dict(
            environment_binding=self.binding, baseline=self.baseline,
            initial_start=self.start.initial, provider=self.initial,
            export=self.initial_export, actor_actions=0))
        self.events.append('observe_initial')

    def record(self, page):
        self._bound_page(page)
        if self.initial is None:
            raise ValueError('Initial state required')
        snapshot = normal.read_snapshot(page)
        http = terminal_document_evidence(page)
        path = urlsplit(page.url).path
        document = dict(url=page.url, http_status=http['http_status'],
            login_page=path.rstrip('/')=='/login',
            error_page=is_error_document(page.url, http['http_status'], page.title()))
        snapshot = ordered.observe_provider(page, snapshot, self.responses, document)
        self.current_export = snapshot
        self.transport.observe(page, snapshot)
        # Only snapshots attached to actual requests are retained by transport;
        # do not rewrite a growing full-page timeline for every observation.
        return deepcopy(snapshot)

    def capture_terminal(self, page, terminal):
        if self.terminal is not None or terminal.get('url') != page.url:
            raise ValueError('One actual matching terminal document required')
        self.record(page)
        self.terminal = deepcopy(terminal)
        self.events.append('capture_terminal')

    def before_action(self, page):
        # Refresh before the action rather than rely on a frame from before a
        # potentially long model generation. This performs no environment action.
        return self.record(page)

    def close(self):
        try:
            if self.transport is not None:
                self.transport.close()
                save(self.directory/'native-export-transport.json', self.transport.metadata())
        finally:
            try:
                if self.start is not None:
                    self.start.close()
            finally:
                super().close()

    def score_terminal(self, site, terminal, *, runtime_error=None):
        if site is not self.site or self.scored or self.terminal is None or terminal != self.terminal:
            raise ValueError('One bound terminal-only scoring call required')
        self.scored = True
        integrity = False
        try:
            site.provider_environment.require_owned()
            site.reset_guard.require_unchanged()
            integrity = site.fingerprint()==self.baseline and site.native_provider_binding==self.binding
        except Exception:
            pass
        args = dict(contract=self.c, page=terminal, answer=None,
            initial=self.initial_export, current=self.current_export, reference=self.reference,
            site_origin=site.url, initial_provider=self.initial, server=self.server,
            integrity=integrity, runtime_error=runtime_error)

        def unknown(reason):
            return dict(version=ordered.VERSION, status='unknown', reward=None, checks={}, reason=reason)

        if runtime_error or not integrity:
            judgment = unknown('Runtime or state integrity unavailable.')
        else:
            try:
                items = self.transport.audit(self.directory/'browser-downloads')
                judgments = []
                for item in items:
                    event = item['event']
                    if not event['native']:
                        continue
                    status = event['response']['http_status']
                    if type(status) is not int or status >= 500:
                        raise ValueError('Native attachment service unavailable')
                    try:
                        parsed = artifact.parse_xml(item['payload'])
                    except ValueError:
                        continue
                    if not parsed['in_bbox_nodes']:
                        continue
                    from .map_osm_native_reference import capture_complete_reference
                    from probe_map_osm_export_capability_v3 import fetch
                    bbox = artifact.request_bbox(event['url'], site.url)
                    ident = str(item['record']['download_id'])
                    _, _, ref, _ = capture_complete_reference(site, bbox, self.directory,
                        'ordered-download-'+ident, fetcher=fetch)
                    download = dict(metadata=dict(event['response'], **item['record']),
                        file=item['file'], private_native_reference=ref)
                    candidate = ordered.evaluate(**args, download=download, transport_event=event)
                    judgments.append(candidate)
                    if candidate['status']=='success':
                        break
                judgment = next((j for j in judgments if j['status']=='success'), None)
                if judgment is None:
                    judgment = next((j for j in judgments if j['status']=='unknown'), None)
                if judgment is None:
                    judgment = judgments[-1] if judgments else ordered.evaluate(**args, download=None, transport_event=None)
            except (ValueError, RuntimeError, OSError, KeyError, TypeError):
                judgment = unknown('Native attachment, provider or independent reference capture unavailable.')
        self.events.append('score_terminal')
        save(self.directory/'ordered-export-terminal.json', dict(events=self.events,
            environment_binding=self.binding, baseline=self.baseline,
            terminal=self.terminal, integrity=integrity, judgment=judgment))
        return judgment, integrity
