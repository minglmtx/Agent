"""Actual normal terminal hook slot; CPU construction is measurement only."""
from copy import deepcopy
import json,hashlib,time
from pathlib import Path
from urllib.parse import urlsplit
from lab_generate_skill import map_history_layer_normal as normal
from lab_generate_skill import map_history_layer_runtime as runtime
from lab_generate_skill.io_utils import atomic_write_json
from lab_generate_skill.map_native_facts_runtime import NativeFactsReadHooks
from lab_generate_skill.map_native_facts_normal import FactsTimeline
from lab_generate_skill.map_native_layer_runtime import NativeLayerHooks
from lab_generate_skill.map_route_normal_capture import NativeRouteCapture,native_request,exact_pair

# These original native controllers/settings/renderers are actually read at
# preparation. The private frontend copies retain the published refresh/index.
LAYER_SOURCE_FILES=tuple(normal.NATIVE_FILES['local_layer'])

class LayerMeasurement(NativeLayerHooks):
 def __init__(self,c,p,directory):
  self.contract=deepcopy(c);self.contract['map_native_layer']={'native_batch_seconds':300}
  self.scope=deepcopy(c['protocol']['completion']);self.directory=Path(directory)
  self.directory.mkdir(parents=True,exist_ok=False)
  self.native={'baseline':p['full_native_baseline']};self.controls_only=True;self.site=None
  self.initial=None;self.baseline=None;self.initial_route=None;self.current=None;self.transport=None
  self.notes=[];self.served=None;self.served_record=None;self.page=None;self.closed=False
  self.notes_handler=None;self.faults=[];self.data_reference_cache={}
  self.installed_native_sha256=deepcopy(p['installed_native_sha256'])

class FiniteTimeline(FactsTimeline):
 def __init__(self,c,directory,proof):
  super().__init__(c,directory);self.proof=proof;self.history_pending=[];self.history_responses=[];self.layer=None;self.route_capture=None
 def attach(self,context):
  super().attach(context)
  if self.c['protocol']['kind']=='local_layer':
   self.route_capture=NativeRouteCapture(context,self.site.route_urls,self.directory/'actual-route-responses')
   if len(context.pages)!=1:raise ValueError('One original normal page before first document required')
   self.layer.attach(context.pages[0],self.site.url)
 def response(self,response):
  super().response(response)
  if self.site and urlsplit(response.url).netloc==urlsplit(self.site.url).netloc and urlsplit(response.url).path=='/history':
   self.history_pending.append(response)
 def observe_initial(self,page):
  super().observe_initial(page)
  if self.layer:
   page.wait_for_function("() => !!document.querySelector('#sidebar_content tr.turn') || !!document.querySelector('#sidebar_content .search_results_error')",timeout=30000)
   self.layer.observe_initial(page)
 def consume_history_responses(self):
  # Consume already observed responses outside the response callback. A
  # private independent /history HTTP request cannot stand in for actual UI.
  for response in self.history_pending:
   raw=response.body();name='actual-history-'+str(len(self.history_responses))+'.html';path=self.directory/name
   path.write_bytes(raw)
   receipt={'requested_url':response.url,'http_status':response.status,'full_body_file':name,
    'full_body_sha256':hashlib.sha256(raw).hexdigest(),'full_body_bytes':len(raw),
    'native_only':True,'external_fallback':False,'complete_transport':True}
   rp=path.with_suffix(path.suffix+'.receipt.json');atomic_write_json(rp,receipt)
   self.history_responses.append({'body':normal.locator(path),'receipt':normal.locator(rp)})
  self.history_pending=[]
 def record(self,page,*,event='issued_observation'):
  if event not in ('issued_observation','terminal'):raise ValueError('Actual ordinary observation required')
  from lab_generate_skill.map_view import read_map_view
  from lab_generate_skill.map_place_page import read_place_page
  row={'sequence':len(self.records),'event':event,'path':urlsplit(page.url).path,'view':read_map_view(page)}
  kind=self.c['protocol']['kind']
  if kind=='named_history':
   from lab_generate_skill.map_list_page import read_list_page
   row['history']=read_list_page(page);self.consume_history_responses();row['native_history_responses']=deepcopy(self.history_responses)
  elif kind=='native_store_exists':row['place']=read_place_page(page)
  else:
   self.layer.record(page,event='terminal'if event=='terminal'else'observation')
   row['layer_surface']=deepcopy(self.layer.current)
   if self.route_capture.first_error:raise ValueError('Complete native route capture failed')
   for response in reversed(self.route_capture.responses):
    if response.get('complete_native_response')is True and response['profile']=='car'and exact_pair(response['pair'],self.c['protocol']['original_route_pair']):
     body=self.route_capture.directory/response['artifact_file'];raw=body.read_bytes()
     if hashlib.sha256(raw).hexdigest()!=response['response_sha256']or json.loads(raw)!=response['body']:raise ValueError('Actual native route response bytes changed')
     row.update(actual_route_body=deepcopy(response['body']),actual_route_request_verified=True,
       actual_route_response_body=normal.locator(body),actual_route_response_metadata=deepcopy(response));break
  self.records.append(row);self.save();return deepcopy(row)
 def capture_terminal(self,page,terminal):
  if self.layer:
   self.layer.terminal(page,terminal)
   value=self.layer.evaluate(self.site,terminal)
   row=self.record(page,event='terminal');row['native_layer_checks']=deepcopy(value['checks'])
   row['native_layer_original_judgment']=value
   row['layer_initial']=deepcopy(self.layer.baseline or self.layer.initial)
   row['layer_original_initial']=deepcopy(self.layer.initial)
   row['layer_initial_route']=deepcopy(self.layer.initial_route)
   row['layer_terminal_route']=deepcopy(terminal['map_native_layer_route'])
   row['layer_served_record']=deepcopy(self.layer.served_record)
   row['layer_notes_responses']=deepcopy(self.layer.notes)
   row['layer_data_transport_records']=deepcopy(self.layer.transport.records if self.layer.transport else [])
   row['layer_directory']=str(self.layer.directory.resolve());self.records[-1]=row;self.save()
  else:self.record(page,event='terminal')
 def close(self):
  try:
   if self.layer:self.layer.close()
   if self.route_capture:self.route_capture.close()
  finally:super().close()

class FiniteHooks(NativeFactsReadHooks):
 def __init__(self,c,p,directory,*,controls_only=False):
  runtime.validate(c)
  if not controls_only:runtime.require_admission(c,p)
  self.contract=deepcopy(c);self.proof=deepcopy(p);self.core=FiniteTimeline(c,Path(directory)/'native-finite',p)
  self.site=None;self.context=None;self.trace_provided=False;self.scored=False;self.answer=None
 def prepare(self,site,username):
  super().prepare(site,username)
  base=Path(site.root)/'datasets/webarena-map-frontend/openstreetmap-website'
  for row in self.proof['native_source_provenance']:
   path=base/row['original_native_relative_path']
   if sha256(path.read_bytes())!=row['original_sha256']:raise ValueError('Actual installed native History/store/layer source changed')
  if self.contract['protocol']['kind']=='local_layer':
   self.core.layer=LayerMeasurement(self.contract,self.proof,self.core.directory/'layer');self.core.layer.prepare(site)
 def score_terminal(self,site,terminal,*,runtime_error=None):
  if site is not self.site or self.scored or not self.trace_provided:raise ValueError('One terminal follows original completed trace')
  self.scored=True;integrity=False
  try:
   site.reset_guard.require_unchanged();integrity=site.fingerprint()==self.proof['full_native_baseline']
   result=normal.judge(self.contract,self.proof,self.core.initial,self.core.records[-1],terminal,self.answer,site_origin=site.url)if integrity and runtime_error is None else None
  except Exception:result=None
  if result is None:result={'version':normal.VERSION,'status':'unknown','reward':None,'checks':{'complete_native_protection_certified':integrity},'reason':'Actual original protected terminal/native evidence incomplete'}
  return result,integrity

def session(site,c,p,directory):
 from lab_generate_skill.gobrowse_runtime import BrowserTask
 from run_site_navigation_once import make_session
 hooks=FiniteHooks(c,p,directory,controls_only=True);hooks.prepare(site,None)
 task=BrowserTask(task_id=c['task_id'],domain='map',goal=runtime.public_goal(c),start_url=site.url+c['start_path'])
 try:
  s=make_session(site,c,Path(directory),{},native_read_hooks=hooks)(None,task);obs,_=s.reset(42)
  if not obs.get('axtree_txt','').strip():raise ValueError('Actual normal initial AX missing')
 except BaseException:hooks.close();raise
 return s,hooks

def sha256(raw):return hashlib.sha256(raw).hexdigest()
