"""Terminal print-artifact lifecycle, with private native route evidence.

No admission is granted here. A reviewed adapter must separately bind the full
public task, environment, reset and reference. This hook never navigates to an
answer, prints for the actor, or supplies private route rows to actor feedback.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
import json
from .io_utils import atomic_write_json
from .map_route_print import capture_source,evaluate_artifact,require_reference
from .map_route_normal_capture import NativeRouteCapture
from .browser_http_status import terminal_document_evidence

VERSION='native-route-print-episode-v1'


def evaluate_saved(directory,reference,*,site_origin,print_source_calls,runtime_error=None,integrity=True):
    directory=Path(directory)
    def result(status,reason,checks=None):
        return dict(version=VERSION,status=status,reward=None if status=='unknown'else float(status=='success'),checks=checks or {},reason=reason)
    if runtime_error or integrity is not True:return result('unknown','Runtime or state integrity is unavailable.')
    try:
        require_reference(reference)
        if type(print_source_calls)is not int or print_source_calls<0:raise ValueError('Missing print lifecycle accounting')
        manifest=directory/'prints.json'
        if not manifest.exists():
            if print_source_calls:raise ValueError('Observed print has no persisted receipt')
            return result('failure','No PDF was printed.',{'pdf_saved':False})
        if manifest.is_symlink():raise ValueError('Print manifest must be a regular artifact')
        payload=json.loads(manifest.read_text());rows=payload['prints']
        # The recorder reads the native source before AND after rendering.
        if not isinstance(rows,list)or 2*len(rows)!=print_source_calls:
            raise ValueError('Print receipts and observed lifecycle differ')
        seen=set();judgments=[]
        for row in rows:
            ident=row['print_id']
            if type(ident)is not int or ident<1 or ident in seen:raise ValueError('Distinct actual print identity required')
            seen.add(ident)
            if row.get('status')!='completed':raise ValueError('Print renderer/capture did not finish')
            name='print-'+str(ident).zfill(4)+'.pdf'
            if row.get('filename')!=name:raise ValueError('Unexpected artifact path')
            pdf=directory/name;source_file=directory/('source-'+str(ident).zfill(4)+'.json')
            if pdf.is_symlink()or source_file.is_symlink():raise ValueError('Print artifact cannot be redirected')
            source=json.loads(source_file.read_text());judgments.append(evaluate_artifact(pdf.read_bytes(),row,source,reference,site_origin=site_origin))
        if seen!=set(range(1,len(rows)+1)):raise ValueError('Missing print record')
        # A corrupt/missing recorded artifact must not be hidden by another
        # valid PDF: persist and diagnose the integrity problem first.
        if any(j['status']=='unknown'for j in judgments):return result('unknown','Printed document evidence is incomplete.')
        found=next((j for j in judgments if j['status']=='success'),None)
        if found:return result('success',found['reason'],dict(found['checks'],pdf_saved=True))
        return result('failure','No saved PDF contains the requested complete route.',{'pdf_saved':bool(rows),'requested_route_printed':False})
    except (KeyError,TypeError,ValueError,OSError,ImportError):return result('unknown','Print lifecycle, artifact or reference evidence is incomplete.')


class PrintEpisodeHooks:
    def __init__(self,candidate,directory,*,reference,baseline):
        require_reference(reference)
        self.c=deepcopy(candidate);self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.reference=deepcopy(reference);self.baseline=baseline
        self.site=self.context=self.page=self.capture=self.initial=self.terminal=None
        self.print_source_calls=0;self.scored=False;self.closed=False
    def prepare(self,site,username):
        if self.site is not None or site.fingerprint()!=self.baseline:raise ValueError('One verified clean native print website required')
        site.reset_guard.require_unchanged();self.site=site
    def attach(self,context):
        if self.site is None or self.context is not None:raise ValueError('One print browser context required')
        self.context=context;self.capture=NativeRouteCapture(context,self.site.route_urls,self.directory/'print-native-responses')
    def observe_initial(self,page):
        if self.initial is not None or page.context is not self.context:raise ValueError('One bound actual initial page required')
        expected=urlsplit(self.site.url+self.c['start_path']);actual=urlsplit(page.url)
        if expected!=actual:raise ValueError('Declared print task initial document changed')
        status=terminal_document_evidence(page)
        if status['http_status']!=200:raise ValueError('Initial print task page unavailable')
        self.page=page;self.initial=dict(url=page.url,http_status=status['http_status'])
        atomic_write_json(self.directory/'print-initial.json',self.initial)
    def record(self,page):
        if self.scored or self.closed or self.initial is None or page is not self.page or page.context is not self.context:
            raise ValueError('Only the active bound print page may supply evidence')
    def capture_print_source(self,page):
        self.record(page);self.print_source_calls+=1
        return capture_source(page,self.capture)
    def capture_terminal(self,page,terminal):
        self.record(page)
        if self.terminal is not None or terminal.get('url')!=page.url:raise ValueError('One actual matching terminal page required')
        self.terminal=deepcopy(terminal)
    def close(self):
        if self.capture is not None:self.capture.close()
        self.closed=True
    def score_terminal(self,site,terminal,*,runtime_error=None):
        if self.scored or not self.closed or site is not self.site or self.terminal is None or terminal!=self.terminal:
            raise ValueError('One completed terminal-only print judgment required')
        self.scored=True;integrity=False
        try:
            site.reset_guard.require_unchanged();integrity=site.fingerprint()==self.baseline
        except (RuntimeError,ValueError):pass
        judgment=evaluate_saved(self.directory/'browser-prints',self.reference,site_origin=site.url,print_source_calls=self.print_source_calls,runtime_error=runtime_error,integrity=integrity)
        atomic_write_json(self.directory/'print-terminal.json',dict(initial=self.initial,terminal=self.terminal,print_source_calls=self.print_source_calls,integrity=integrity,judgment=judgment))
        return judgment,integrity
