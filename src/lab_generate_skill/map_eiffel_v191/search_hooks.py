"""Observe native search only; background map rendering does not gate results."""
from pathlib import Path
from copy import deepcopy
from urllib.parse import urlsplit
import json,time
from lab_generate_skill.io_utils import atomic_write_json as save
from lab_generate_skill.map_place_page import READ
from lab_generate_skill.map_native_facts_normal import FactsTimeline
from .evaluate import evaluate
class SearchHooks(FactsTimeline):
 def __init__(self,candidate,directory,*,reference):
  # FactsTimeline's response/lookup methods are reused unchanged; its map-tile
  # readiness and original task-specific serialization are not this scope.
  self.c=deepcopy(candidate);self.directory=Path(directory);self.directory.mkdir(exist_ok=True)
  self.reference=deepcopy(reference);self.records=[];self.requests=[];self.initial=None;self.context=None;self.site=None;self.terminal=None;self.closed=False;self.errors=[];self.failed_requests=[];self.pending=set();self.baseline=None
 def save(self):
  save(self.directory/'search-observations.json',dict(initial=self.initial,samples=self.records,native_request_metadata=self.requests,errors=self.errors,failed_requests=self.failed_requests,pending_search_requests=sorted(self.pending),terminal=self.terminal,closed=self.closed,browser_actions_created=0,background_map_readiness_required=False))
 def prepare(self,site,username):
  if self.site is not None or username is not None:raise ValueError('One anonymous native search episode required')
  site.reset_guard.require_unchanged();self.site=site;self.baseline=site.fingerprint()
 def matches(self,url):
  a,b=urlsplit(url),urlsplit(self.site.url);return(a.scheme,a.netloc)==(b.scheme,b.netloc)and a.path=='/geocoder/search_osm_nominatim'
 def requested(self,request):
  if self.matches(request.url):self.pending.add(request.url)
 def finished(self,request):
  if self.matches(request.url):self.pending.discard(request.url)
 def failed(self,request):
  if self.matches(request.url):self.pending.discard(request.url);self.failed_requests.append(dict(url=request.url,failure=request.failure))
 def attach(self,context):
  super().attach(context);context.on('request',self.requested);context.on('requestfinished',self.finished);context.on('requestfailed',self.failed)
 def observe_initial(self,page):
  h=json.loads((self.directory/'initial-page-health.json').read_text())
  if self.initial is not None or h['url']!=page.url:raise ValueError('One actual original page required')
  self.initial=dict(h,actor_actions=0);self.save()
 def record(self,page,*,event='observation'):
  if self.closed or page.context is not self.context or self.initial is None:raise ValueError('Bound live ordinary context required')
  state=page.evaluate(READ);end=time.monotonic()+15;stable=None;since=time.monotonic()
  while True:
   signal=(state['path'],state['query'],state['loading'],len(state['results']),len(state['tags']),tuple(sorted(self.pending)))
   now=time.monotonic()
   if signal!=stable:stable=signal;since=now
   if(not state['loading']and not self.pending and now-since>=.25)or now>=end:break
   page.wait_for_timeout(50);state=page.evaluate(READ)
  row=dict(sequence=len(self.records),event='terminal'if event=='terminal'else'issued_observation',path=state['path'],place=state)
  if event=='terminal':
   # The reused lookup helper's map animation test is outside this new scope.
   # Keep the actual captured state unchanged and project only for that helper.
   projected=dict(row,place=dict(state,map_async_loading=False));self.lookup_current_native_results(projected)
   row.update({k:v for k,v in projected.items()if k not in ('place','path','sequence','event')})
   row['lookup_projection_ignored_background_map_animation']=True
  self.records.append(row);self.save();return deepcopy(row)
 def capture_terminal(self,page,terminal):
  if self.terminal is not None or terminal['url']!=page.url:raise ValueError('One actual terminal required')
  try:self.record(page,event='terminal')
  except Exception as exc:self.errors.append(dict(type=type(exc).__name__,message=str(exc)))
  self.terminal=deepcopy(terminal);self.save()
 def close(self):
  if not self.closed:
   if self.context is not None:
    self.context.remove_listener('request',self.requested);self.context.remove_listener('requestfinished',self.finished);self.context.remove_listener('requestfailed',self.failed)
   super().close();self.closed=True;self.save()
 def score_terminal(self,site,terminal,*,runtime_error=None):
  if site is not self.site or terminal!=self.terminal or not self.closed:raise ValueError('Closed matching search episode required')
  integrity=False
  try:site.reset_guard.require_unchanged();integrity=site.fingerprint()==self.baseline
  except Exception:pass
  transport=self.failed_requests or self.pending or [r for r in self.requests if r.get('http_status')!=200 or r.get('actual_request_capture_error')]
  judgment=evaluate(self.c,reference=self.reference,initial=self.initial,page=terminal,samples=self.records,observation_directory=self.directory,site_origin=site.url,search_url=site.search_url,integrity=integrity,runtime_error=runtime_error or self.errors,search_transport_error=transport)
  save(self.directory/'search-terminal.json',dict(judgment=judgment,integrity=integrity,baseline=self.baseline,site_origin=site.url,search_url=site.search_url,closed=self.closed))
  return judgment,integrity
