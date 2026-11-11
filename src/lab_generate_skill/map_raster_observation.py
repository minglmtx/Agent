"""Initial-bound PNG reference and actual terminal downloads.

The actor context is only observed. A separate anonymous reference context reads
the default native export form before inference; no download is manufactured in
the actor context. Reference rendering is private and excluded from its receipts.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import urllib.request

from .map_candidate_start import InitialStartHooks
from .map_raster_request import normalize, export_byte_limit
from .map_raster_artifact import decode
from .map_raster_downloads import evaluate_downloads,artifact_backend
from .browser_request_policy import install_local_network_policy
from .io_utils import atomic_write_json as save

READER='() => window.__labShareState()'
EXPORT_REQUEST_READER='''form => {
  const value = name => {
    const field = form.querySelector('[name="'+name+'"]');
    if (!field || !field.value.trim()) throw Error('Native export field absent: '+name);
    return field.value;
  };
  const route = jQuery(form).data('labRasterRoute');
  if (typeof route !== 'function') throw Error('Native route reader absent');
  return {bbox:['minlon','minlat','maxlon','maxlat'].map(n => Number(value(n))),
          scale:Number(value('mapnik_scale')),format:value('mapnik_format'),route:route()};
}'''


def require_same_view(first, second):
    for key in ('zoom','size','bounds'):
        if first[key]!=second[key]:raise ValueError('Independent initial map geometry differs: '+key)
    for key in ('lat','lng'):
        if abs(first['center'][key]-second['center'][key])>1e-9:
            raise ValueError('Independent initial map center differs')


def render_reference(site,request):
    file_format=request.get('format')
    decode_artifact,_=artifact_backend(file_format)
    normalized=normalize(request,allow_pdf=file_format=='pdf')
    mime='application/pdf' if file_format=='pdf' else 'image/png'
    req=urllib.request.Request(site.raster_url,data=json.dumps(request).encode(),
                               headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=100)as response:
        if response.status!=200 or response.headers.get_content_type()!=mime:
            raise ValueError('Owned native renderer unavailable')
        body=response.read(export_byte_limit(file_format)+1)
    if decode_artifact(body).size!=(normalized['width'],normalized['height']):
        raise ValueError('Private native reference dimensions differ')
    return body


def initial_reference(site,candidate,actor_page,initial,directory):
    """No actor-selected artifact participates in constructing this reference."""
    from browsergym.core import _get_global_playwright
    actor_state=actor_page.evaluate(READER)
    browser=_get_global_playwright().chromium.launch(headless=True)
    context=browser.new_context(viewport=actor_page.viewport_size,locale='en-US')
    install_local_network_policy(context,site.allowed_netlocs)
    hooks=InitialStartHooks(candidate,site);hooks.attach(context)
    try:
        page=context.new_page();page.set_default_timeout(15000)
        response=page.goto(site.url+candidate['start_path'],wait_until='domcontentloaded',timeout=30000)
        if response is None or response.status!=200:raise ValueError('Independent initial page unavailable')
        hooks.observe_initial(page);state=page.evaluate(READER)
        require_same_view(actor_state,state)
        if hooks.initial['route']!=initial['route']:
            raise ValueError('Independent initial route differs')
        page.locator('.control-share .control-button').click()
        form=page.locator('#export-image');form.wait_for(state='visible',timeout=15000)
        if candidate['candidate_completion']['family']=='pdf_artifact':
            form.locator('#mapnik_format').select_option('pdf')
        from .map_raster_scale import multiplier, target_scale
        initial_public_request=form.evaluate(EXPORT_REQUEST_READER)
        if multiplier(candidate) != 1:
            field = form.locator('#mapnik_scale')
            field.fill(target_scale(candidate, field.input_value()))
        # Match ExportController's mapnik_* fields. Hidden `format=mapnik`
        # selects the export handler; it is not the image encoding.
        request=form.evaluate(EXPORT_REQUEST_READER)
        normalize(request,allow_pdf=candidate['candidate_completion']['family']=='pdf_artifact')
        if bool(request['route'])!=candidate['candidate_completion']['retain_route']:
            raise ValueError('Initial route inclusion differs from declared task')
        body=render_reference(site,request)
        # The private page must not pan, expand, or otherwise change actor state.
        require_same_view(actor_state,actor_page.evaluate(READER))
        reference=dict(request=request,initial_public_request=initial_public_request,
                       initial=deepcopy(initial),native_state=actor_state,
                       independent_initial=hooks.initial,anonymous_context=True,
                       before_actor_inference=True,actor_context_actions=0,
                       sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
        return reference,body
    finally:
        hooks.close();context.close();browser.close()


class RasterObservationHooks(InitialStartHooks):
    def __init__(self,candidate,directory,*,baseline,reference_factory=initial_reference):
        spec=candidate.get('candidate_completion',{})
        if (spec.get('family')not in ('png_artifact','pdf_artifact')
                or type(spec.get('retain_route'))is not bool or not candidate.get('goal_revision')):
            raise ValueError('Publicly declared initial/default map export contract required')
        from .map_raster_scale import multiplier
        multiplier(candidate)
        self.file_format='pdf' if spec['family']=='pdf_artifact' else 'png'
        if self.file_format=='pdf' and spec.get('format')!='PDF':
            raise ValueError('PDF task format must be publicly declared')
        super().__init__(deepcopy(candidate),None)
        self.directory=Path(directory);self.baseline=baseline;self.reference_factory=reference_factory
        self.page=self.reference=self.trace=None;self.closed=self.scored=False
        self.reference_body=b'';self.receipt_offset=None;self.receipt_inode=None;self.receipt_path=None

    def prepare(self,site,username):
        if self.site is not None or username is not None or site.domain!='map':
            raise ValueError('One anonymous native PNG preparation required')
        if not all(getattr(site,k,False)for k in ('with_tiles','with_geographic_baseline','track_changes','native_share_observer','raster_installed')):
            raise ValueError('Guarded native renderer profile required')
        if self.file_format=='pdf' and getattr(site,'allow_pdf',False)is not True:
            raise ValueError('Native PDF environment profile is not enabled')
        site.reset_guard.require_unchanged()
        if not self.baseline or site.fingerprint()!=self.baseline:raise ValueError('PNG source baseline changed')
        self.site=site;self.events.append('prepare')

    def observe_initial(self,page):
        if self.page is not None:raise ValueError('One original PNG initial observation required')
        super().observe_initial(page);self.page=page
        self.reference,body=self.reference_factory(self.site,self.candidate,page,self.initial,self.directory)
        self.reference_body=body
        private=self.directory/(self.file_format+'-reference');private.mkdir(exist_ok=False)
        (private/('reference.'+self.file_format)).write_bytes(body);save(private/'initial.json',self.reference)
        self.receipt_path=self.site.state/'tiles/raster-receipts.jsonl'
        # Keep only current attempt's service receipts. Private rendering and
        # previous episodes must not supply actor-output provenance.
        self.receipt_offset=self.receipt_path.stat().st_size
        self.receipt_inode=self.receipt_path.stat().st_ino
        self.site.reset_guard.require_unchanged()

    def close(self):
        if not self.closed:super().close();self.closed=True

    def provide_trace(self,trace):
        if self.trace is not None or not isinstance(trace,dict)or self.scored:
            raise ValueError('One completed trace required')
        self.trace=trace;self.events.append('provide_trace')

    def score_terminal(self,site,terminal,*,runtime_error=None):
        if site is not self.site or self.scored or not self.closed or self.trace is None or terminal!=self.terminal:
            raise ValueError('One bound PNG terminal score after context closure required')
        self.scored=True;self.events.append('score_terminal');integrity=False;receipts=None;capture_error=None
        try:
            site.reset_guard.require_unchanged();integrity=site.fingerprint()==self.baseline
            stat=self.receipt_path.stat()
            if stat.st_ino!=self.receipt_inode or stat.st_size<self.receipt_offset or stat.st_size-self.receipt_offset>16*1024*1024:
                raise ValueError('Native renderer receipt stream replaced or unbounded')
            with self.receipt_path.open('rb')as f:
                f.seek(self.receipt_offset);raw=f.read()
            if raw and not raw.endswith(b'\n'):raise ValueError('Renderer receipt write incomplete')
            receipts=[json.loads(line)for line in raw.splitlines()]
        except Exception as error:capture_error=type(error).__name__+': native renderer evidence unavailable'
        judgment=evaluate_downloads(self.directory/'browser-downloads',
            expected_request=(self.reference or {}).get('request'),reference_body=self.reference_body,
            receipts=receipts,runtime_error=runtime_error or capture_error,integrity=integrity,file_format=self.file_format)
        save(self.directory/(self.file_format+'-terminal.json'),dict(events=self.events,terminal=terminal,
            reference_file=self.file_format+'-reference/initial.json',receipts=receipts,receipt_offset=self.receipt_offset,
            integrity=integrity,capture_error=capture_error,judgment=judgment))
        return judgment,integrity
