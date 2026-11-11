"""Finite native information/readout protocols with normal BrowserGym hooks.

Private source controls and references never become actor actions or observations.
Original goals and first starts stay intact. Finite fields below are explicitly a
local interpretation of open reading tasks, not an equivalence claim to the
publisher's model judge. Unsupported original predicates remain unknown.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import hashlib, json, re, time

from lab_generate_skill.io_utils import atomic_write_json
from lab_generate_skill.map_local_capabilities import document_content
from lab_generate_skill.map_typed_information_share import document_values, read_share_state
from lab_generate_skill.map_document_query import captured_values
from lab_generate_skill.map_place_identity import identity, bounds, public_result_matches, native_view_in_place
from lab_generate_skill.map_place_page import read_place_page
from lab_generate_skill.map_view import READ as READ_NATIVE_VIEW, read_map_view, wait_native_view
from lab_generate_skill.site_query_rules import evaluate_query
from lab_generate_skill.site_navigation_rules import valid_initial_page

VERSION = 'full-native-facts-normal-v1'
DOCS = {
 'local_chapters': {'paths': ['/communities'], 'fields': {'chapters':'record_set','chapter_definition':'string'},
    'record_fields':{'chapters':{'name':'string'}},
    'field_meanings':{'chapters':'All Local Chapters listed by this native page; no external chapter visit is required.',
                      'chapter_definition':'The native paragraph defining Local Chapters.'}},
 'contributors_and_sources': {'paths':['/about','/copyright'],
    'fields':{'groups':'record_set','source_overview':'string','sources':'record_subset'},
    'record_fields':{'groups':{'description':'string'},'sources':{'country':'string','description':'string'}},
    'minimum_records':{'sources':1},
    'field_meanings':{'groups':'All contributor groups named in the native About document.',
                      'source_overview':'The native introduction to the contributors and sources of map data.',
                      'sources':'At least one distinct country/source example from the native Copyright document.'}},
 'contribution_information': {'paths':['/about'],
    'fields':{'mapping_context':'string','verification_methods':'record_set'},
    'record_fields':{'verification_methods':{'name':'string'}},
    'field_meanings':{'mapping_context':'The native paragraph describing the data contributed and maintained by community mappers.',
                      'verification_methods':'All verification methods named by Local Knowledge in the native About document; no editing action is requested.'}},
 'community_and_contributors': {'paths':['/about'],
    'fields':{'community_overview':'string','groups':'record_set'},
    'record_fields':{'groups':{'description':'string'}},
    'field_meanings':{'community_overview':'The native paragraph introducing OpenStreetMap community mappers.',
                      'groups':'All contributor groups named in the native About document.'}},
}


def fingerprint(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def source_binding(c):
 value = {k:deepcopy(c[k])for k in ('source_task_id','domain','goal','family','start_path','original_recorded_starts','source_trace_ids','aliases','original_binding_sha256','heldout_quarantine','initialization_revision','protocol')}
 if c.get('goal_revision'):
  from .source_revision_binding import binding
  value.update(task_id=c['task_id'], goal_revision=deepcopy(c['goal_revision']), source_revision_binding=binding(c))
 return value


def section(body,path,heading,next_heading):
 content=document_content(body,path)
 lines=[' '.join(v.split())for v in content.splitlines()if v.strip()]
 if lines.count(heading)!=1 or lines.count(next_heading)!=1:raise ValueError('Native section anchor missing or ambiguous')
 a,b=lines.index(heading),lines.index(next_heading)
 if b<=a+1:raise ValueError('Native section is empty or reversed')
 return ' '.join(lines[a+1:b])


def mapping_context(body):
 content=document_content(body,'/about')
 paragraphs=[' '.join(v.split())for v in content.splitlines()if v.strip()]
 matches=[v for v in paragraphs if v.startswith('OpenStreetMap is built by a community of mappers')]
 if len(matches)!=1:raise ValueError('The native community introduction is absent or ambiguous')
 return matches[0]


def doc_values(kind,documents):
 if kind not in DOCS or set(documents)!=set(DOCS[kind]['paths']):raise ValueError('Full exact document scope required')
 for path,row in documents.items():
  if (row.get('requested_path')!=path or row.get('http_status')!=200 or not isinstance(row.get('body'),str)
      or not row['body'].strip() or row.get('full_native_body')is not True):
   raise ValueError('Full healthy native document required')
 if kind=='local_chapters':
  row=documents['/communities']
  return {'chapters':captured_values(row,'chapters')['items'],
          'chapter_definition':section(row['body'],'/communities','Local Chapters','The following communities are formally established as Local Chapters:')}
 about=documents['/about']['body']
 if kind=='contribution_information':
  text=section(about,'/about','Local Knowledge','Community Driven')
  matches=re.findall(r'Contributors use (.*?) to verify that OSM is accurate and up to date\.',text)
  if len(matches)!=1:raise ValueError('Native contribution verification methods absent or ambiguous')
  names=[v.strip()for v in re.split(r', (?:and )?| and ',matches[0])]
  if len(names)<2 or len(set(names))!=len(names)or not all(names):raise ValueError('Native contribution method list malformed')
  return {'mapping_context':mapping_context(about),'verification_methods':[{'name':v}for v in names]}
 groups=document_values('contributor_groups',about)['groups']
 if kind=='community_and_contributors':return {'community_overview':mapping_context(about),'groups':groups}
 sources=document_values('data_sources',documents['/copyright']['body'])
 return {'groups':groups,'source_overview':sources['overview'],'sources':sources['sources']}


def document_projection(c):
 q=deepcopy(DOCS[c['protocol']['kind']]);q.pop('paths')
 q['family']='map_full_native_information'
 return {'domain':'map','task_id':c['source_task_id'],'source_task_id':c['source_task_id'],
         'goal':c['goal'],'start_path':c['start_path'],'query':q}


def public_goal(c):
 if c['protocol']['kind']in DOCS:
  from lab_generate_skill.site_query_rules import query_goal
  return query_goal(document_projection(c))
 return c['goal']


def body_record(page,path):
 """Full actual native body and links, no slices or expected values."""
 from lab_generate_skill.browser_http_status import terminal_document_evidence
 health=terminal_document_evidence(page,{})
 return {'requested_path':path,'url':page.url,'http_status':health['http_status'],
         'body':page.locator('body').inner_text(timeout=10000),
         'links':page.locator('a[href]').evaluate_all('(es)=>es.map(e=>({text:e.innerText,href:e.href}))'),
         'full_native_body':True}


def query_view(state):
 from lab_generate_skill.map_local_capabilities import geo_triplet,map_triplet,same_center
 try:
  a,b=geo_triplet(state),map_triplet(state['native_long_link'])
  if not same_center(a,b)or not state.get('tiles')or state.get('map_visible')is not True:return None
  return list(a)
 except (ValueError,KeyError,TypeError):return None


def wait_rendered_initial_view(page,initial_path,*,timeout=45000):
 """Same native initial view and absolute budget, with actual loaded tiles.

 Native links can settle before the first tile finishes. Private current-view
 references require both; no target, pan, zoom or extra browser action is added.
 """
 deadline=time.monotonic()+timeout/1000
 def remaining():
  value=(deadline-time.monotonic())*1000
  if value<=0:raise TimeoutError('Original rendered map readiness budget elapsed')
  return value
 view=wait_native_view(page,initial_path,timeout=remaining())
 if query_view(view)is not None:return view
 page.wait_for_function('() => ('+READ_NATIVE_VIEW+')().tiles.length > 0',timeout=remaining())
 # Observe native moveend/search auto-pan again, using only the remaining
 # original budget; a loaded unrelated/stale tile cannot bypass coherence.
 view=wait_native_view(page,initial_path,timeout=remaining())
 if query_view(view)is None:raise ValueError('Complete original rendered initial map identity unavailable')
 return view


def native_raw_read(url,directory,name,deadline):
 """Full local response or exact partial failure bytes, before parsing."""
 from urllib.request import urlopen
 from urllib.error import HTTPError
 directory=Path(directory);path=directory/name
 if path.exists():raise ValueError('Never overwrite an actual native response')
 chunks=[];status=None
 try:
  remaining=deadline-time.monotonic()
  if remaining<=0:raise TimeoutError('Original native response deadline elapsed')
  try:response=urlopen(url,timeout=min(30,remaining))
  except HTTPError as error:response=error
  with response:
   status=response.status
   while True:
    if time.monotonic()>=deadline:raise TimeoutError('Original native response deadline elapsed')
    chunk=response.read(65536)
    if not chunk:break
    chunks.append(chunk)
  raw=b''.join(chunks);path.write_bytes(raw)
  receipt={'requested_url':url,'http_status':status,'full_body_file':name,
           'full_body_sha256':hashlib.sha256(raw).hexdigest(),'full_body_bytes':len(raw),
           'native_only':True,'external_fallback':False,'complete_transport':True}
  atomic_write_json(path.with_suffix(path.suffix+'.receipt.json'),receipt)
  return raw,receipt
 except BaseException as error:
  raw=b''.join(chunks);partial=path.with_suffix(path.suffix+'.partial');partial.write_bytes(raw)
  atomic_write_json(path.with_suffix(path.suffix+'.receipt.json'),{'requested_url':url,'http_status':status,
    'complete_transport':False,'partial_body_file':partial.name,'partial_body_sha256':hashlib.sha256(raw).hexdigest(),
    'partial_body_bytes':len(raw),'first_error':{'type':type(error).__name__,'message':str(error)},'native_only':True,'external_fallback':False})
  raise


def actual_geocoder_request(response):
 """Capture actual URL and form-body parameters, without response/network I/O.

 Native search.page.load submits zoom/bounds by POST. These are request
 evidence, not values inferred from a task reference or initial map state.
 Conflicting URL/body values are untrusted and remain a capture error.
 """
 request=response.request
 method=request.method.upper();url_parameters=parse_qs(urlsplit(response.url).query,keep_blank_values=True)
 raw=request.post_data_buffer or b''
 if not isinstance(raw,bytes):raise ValueError('Actual request body bytes unavailable')
 content_type=request.headers.get('content-type','').split(';',1)[0].strip().lower()
 if raw and (method!='POST' or content_type!='application/x-www-form-urlencoded'):
  raise ValueError('Unsupported actual native geocoder request body')
 text=raw.decode('utf-8',errors='strict')
 body_parameters=parse_qs(text,keep_blank_values=True)if raw else{}
 params=deepcopy(url_parameters)
 for key,values in body_parameters.items():
  if key in params and params[key]!=values:raise ValueError('Conflicting actual URL/body geocoder parameters')
  params[key]=values
 return {'url':response.url,'http_status':response.status,'parameters':params,
   'actual_http_method':method,'actual_request_content_type':content_type,
   'actual_request_body_utf8':text,'actual_request_body_bytes':len(raw),
   'actual_request_body_sha256':hashlib.sha256(raw).hexdigest(),
   'actual_url_parameters':url_parameters,'actual_body_parameters':body_parameters,
   'request_only_capture':True,'response_body_read_inside_callback':False}


class FactsTimeline:
 """Use the existing native_read_hooks observation slot; no runner changes."""
 def __init__(self,c,directory,site=None):
  self.c=deepcopy(c);self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=False)
  self.records=[];self.initial=None;self.context=None;self.site=site;self.requests=[]
  if (self.directory/'native-facts-observations.json').exists():raise ValueError('Never clear an existing attempt timeline')
 def save(self):
  atomic_write_json(self.directory/'native-facts-observations.json',{'version':VERSION,'source_binding_sha256':fingerprint(source_binding(self.c)),
    'initial':self.initial,'samples':self.records,'private_expected_values_added_to_actor':False,
    'full_native_data_preserved':True,'browser_action_created':False,
    'native_request_metadata':deepcopy(self.requests)})
 def observe_initial(self,page):
  a,b=urlsplit(page.url),urlsplit(self.c['start_path'])
  if a.path!=b.path or a.query!=b.query:raise ValueError('Original first document changed before normal observation')
  needs_rendered=self.c['protocol']['kind']in('current_view_share','initial_where_is_this','native_pan')
  waiter=wait_rendered_initial_view if needs_rendered else wait_native_view
  view=waiter(page,self.c['start_path'])if b.path in('/','/search','/directions')else None
  self.initial={'original_first_start_preserved':True,'original_start_path':self.c['start_path'],
                'actual_initial_view':view,'native_initial_view_identity':query_view(view)if view else None}
  self.save()
 def attach(self,context):
  if self.context is not None:raise ValueError('Native query listener already attached')
  self.context=context
  context.on('response',self.response)
 def response(self,response):
  # Metadata only: no native network I/O or response-body wait inside a
  # Playwright event callback. Runtime performs independent lookup afterwards.
  u=urlsplit(response.url)
  if self.site is None or u.netloc!=urlsplit(self.site.url).netloc:return
  if u.path in('/geocoder/search_osm_nominatim','/geocoder/search_osm_nominatim_reverse'):
   try:self.requests.append(actual_geocoder_request(response))
   except (ValueError,UnicodeError,AttributeError)as error:
    self.requests.append({'url':response.url,'http_status':response.status,'parameters':{},
      'actual_request_capture_error':{'type':type(error).__name__,'message':str(error)}})
 def capture_terminal(self,page,terminal):
  self.record(page,event='terminal')
 def close(self):
  if self.context is not None:
   self.context.remove_listener('response',self.response);self.context=None
 def record(self,page,*,event='issued_observation'):
  if event not in('issued_observation','terminal'):raise ValueError('Only actual issued observation or terminal is recordable')
  kind=self.c['protocol']['kind'];path=urlsplit(page.url).path
  row={'sequence':len(self.records),'event':event,'path':path}
  if kind in DOCS:
   if path in DOCS[kind]['paths']:
    row['document']=body_record(page,path)
  elif kind=='current_view_share':
   row['share']=read_share_state(page)
   row['view']=read_map_view(page)
  elif kind in('named_place_search','any_native_place_search','named_place_coordinates','initial_where_is_this'):
   if path=='/search'or re.fullmatch(r'/(node|way|relation)/[1-9][0-9]*',path):
    row['place']=read_place_page(page)
    if kind in('any_native_place_search','named_place_search','named_place_coordinates')and event=='terminal':self.lookup_current_native_results(row)
    if kind=='initial_where_is_this'and event=='terminal':self.capture_native_reverse(row)
  from . import map_local_view_facts as local_view
  if kind in local_view.KINDS:
   row.update(local_view.read(page,kind))
   if kind!='native_pan'and event=='terminal':self.lookup_current_native_results(row)
  self.records.append(row);self.save();return deepcopy(row)
 def lookup_current_native_results(self,row):
  if self.site is None:raise ValueError('Actual loopback native geocoder required')
  state=row['place'];q=state.get('query')
  rows=state.get('results',[])
  current=re.fullmatch(r'/(node|way|relation)/([1-9][0-9]*)',state.get('path',''))
  if current:
   # A selected native detail remains a valid search result only if the same
   # object was actually shown by a submitted native query earlier in this
   # attempt. Never fabricate a search from a bare object URL or stale query.
   previous=[r['place']for r in self.records if r.get('place',{}).get('path')=='/search'
             and any(v.get('path')==state['path']for v in r.get('place',{}).get('results',[]))]
   if previous:q=previous[-1]['query'];rows=[v for v in previous[-1]['results']if v.get('path')==state['path']]
   else:q=None;rows=[]
  matching=[r for r in self.requests if r['http_status']==200 and r['parameters'].get('query')==[q]]
  row['actual_submitted_query']=q;row['native_rails_search_response']=deepcopy(matching[-1])if matching else None
  if not q or not matching or state.get('loading')or state.get('map_async_loading'):return
  identities=[]
  for value in rows:
   match=re.fullmatch(r'/(node|way|relation)/([1-9][0-9]*)',value.get('path',''))
   if not match:continue
   code={'node':'N','way':'W','relation':'R'}[match[1]]+match[2]
   if code not in identities:identities.append(code)
  if not identities:return
  from urllib.parse import urlencode
  from urllib.request import urlopen
  # Native lookup identifies precisely the observed OSM objects; it does not
  # select a new target or infer nonexistence from a bounded search page.
  url=self.site.search_url+'/lookup?'+urlencode({'osm_ids':','.join(identities),'format':'jsonv2','addressdetails':1,'namedetails':1,'extratags':1})
  try:
   fname='native-lookup-'+str(len(self.records))+'.body'
   raw,receipt=native_raw_read(url,self.directory,fname,time.monotonic()+30)
   row['independent_native_lookup_transport']=receipt
   records=json.loads(raw)
   if receipt['http_status']!=200 or not isinstance(records,list)or not records:raise ValueError('Complete independent native lookup unavailable')
   returned=[]
   for value in records:
    k,n=identity(value);bounds(value);returned.append({'node':'N','way':'W','relation':'R'}[k]+str(n))
   if len(returned)!=len(set(returned))or set(returned)!=set(identities):raise ValueError('Native lookup does not identify every exact observed object once')
   row['independent_native_lookup']={**receipt,'full_records':records,
     'observed_native_object_ids':identities,'new_target_or_search_query_created':False}
  except Exception as error:
   row['independent_native_lookup_error']={'type':type(error).__name__,'message':str(error)}
 def capture_native_reverse(self,row):
  matching=[r for r in self.requests if urlsplit(r['url']).path=='/geocoder/search_osm_nominatim_reverse'and r['http_status']==200]
  if not matching:return
  actual=matching[-1];params=actual['parameters'];row['native_rails_reverse_response']=deepcopy(actual)
  try:
   from urllib.parse import urlencode
   from urllib.request import urlopen
   import xml.etree.ElementTree as ET
   args={k:params[k][0]for k in('lat','lon')if len(params.get(k,[]))==1}
   if set(args)!=set(('lat','lon')):raise ValueError('Full actual native reverse coordinates required')
   if 'zoom'in params and len(params['zoom'])!=1:raise ValueError('Ambiguous actual native reverse zoom')
   # The actual pinned Rails controller interpolates a missing zoom as an
   # empty query value. Forward that native behavior exactly, never inject
   # the initial map zoom into a request that did not supply one.
   args['zoom']=params.get('zoom',[''])[0]
   url=self.site.search_url+'/reverse?'+urlencode(dict(args,format='xml',**{'accept-language':'en-US,en'}))
   fname='native-reverse-'+str(len(self.records))+'.xml'
   raw,receipt=native_raw_read(url,self.directory,fname,time.monotonic()+30)
   row['independent_native_reverse_transport']=receipt
   if receipt['http_status']!=200:raise ValueError('Native reverse service returned non-200')
   native=ET.fromstring(raw);objects=native.findall('result')
   if len(objects)!=1:raise ValueError('Complete native current-location reverse result missing or ambiguous')
   obj=objects[0];kind=obj.get('osm_type');number=obj.get('osm_id')
   identity({'osm_type':kind,'osm_id':number})
   value={'osm_type':kind,'osm_id':int(number),'lat':obj.get('lat'),'lon':obj.get('lon'),'description':obj.text}
   if not value['description']or not all(value[k]for k in('lat','lon')):raise ValueError('Native reverse object incomplete')
   row['independent_native_reverse']={**receipt,'actual_arguments':args,'full_record':value,
    'native_request_zoom_supplied':'zoom'in params,
    'new_target_or_actor_action_created':False}
  except Exception as error:row['independent_native_reverse_error']={'type':type(error).__name__,'message':str(error)}


def document_judgment(c,proof,timeline,terminal,answer,*,site_origin):
 if proof.get('source_binding_sha256')!=fingerprint(source_binding(c)):
  return {'status':'unknown','reward':None,'checks':{},'reason':'Original source definition changed'}
 try:
  values=doc_values(c['protocol']['kind'],proof['documents'])
 except (ValueError,KeyError)as error:return {'status':'unknown','reward':None,'checks':{},'reason':str(error)}
 ref={'object_id':'map-full-native:'+c['protocol']['kind'],'values':values}
 j=evaluate_query(document_projection(c),terminal,answer,ref,ref,site_origin=site_origin)
 seen={r['path']:r['document']for r in timeline.records if 'document'in r}
 expected=proof['documents'];matched={path:any(r.get('document',{}).get('http_status')==200 and
    r.get('document',{}).get('body')==expected[path]['body']and r.get('path')==path for r in timeline.records)for path in expected}
 j['checks']['full_requested_native_documents_observed']=all(matched.values())
 if j['status']!='unknown':
  j['status']='success'if all(j['checks'].values())else'failure';j['reward']=float(j['status']=='success')
 return j


def current_share_judgment(c,proof,timeline,terminal,answer,*,site_origin):
 from lab_generate_skill.admin_query_rules import parse_answer
 from lab_generate_skill.map_typed_information_share import local_url
 if (proof.get('source_binding_sha256')!=fingerprint(source_binding(c))or not proof.get('initial_view_identity')):
  return {'status':'unknown','reward':None,'checks':{},'reason':'Original rendered initial map reference missing or changed'}
 try:v=parse_answer(answer);schema=set(v)=={'share_link'}
 except (ValueError,TypeError):v={};schema=False
 answer_url=v.get('share_link');seen=[]
 for row in timeline.records[-1:]:
  state=row.get('share',{})
  if state.get('visible')is not True or state.get('map_visible')is not True:continue
  if not(state.get('active_base_labels')==state.get('checked_base_labels')==['Standard']and state.get('active_overlay_labels')==[]):continue
  if any(state.get(k+'_visible')is True and state.get(k+'_value')!=state.get(k+'_href')for k in('long','short')):continue
  normalized={k:urlsplit(state[k]).path+('?' +urlsplit(state[k]).query if urlsplit(state[k]).query else '')+('#'+urlsplit(state[k]).fragment if urlsplit(state[k]).fragment else '')for k in('long_href','short_href')if isinstance(state.get(k),str)}
  if normalized!=proof['native_artifacts']:continue
  if not all(local_url(state.get(k),site_origin)for k in('long_href','short_href')):continue
  if answer_url in(state.get('long_href'),state.get('short_href')):seen.append(state)
 checks={'page_valid':valid_initial_page(terminal,site_origin=site_origin),'answer_schema':schema,
         'native_share_original_view_and_layer_observed':bool(seen),
         'local_native_artifact_returned':bool(schema and local_url(answer_url,site_origin)),
         'original_source_reference_preserved':bool(timeline.initial and timeline.initial.get('native_initial_view_identity')==proof['initial_view_identity'])}
 success=all(checks.values())
 return {'version':VERSION,'status':'success'if success else'failure','reward':float(success),'checks':checks,'reason':None}


def place_judgment(c,proof,timeline,terminal,answer,*,site_origin):
 """No name similarity/first-row rank; actual native identity and map required."""
 if proof.get('source_binding_sha256')!=fingerprint(source_binding(c)):
  return {'status':'unknown','reward':None,'checks':{},'reason':'Original source binding changed'}
 records=proof.get('native_records')
 if c['protocol']['kind']in('named_place_search','named_place_coordinates'):
  last=timeline.records[-1]if timeline.records else{}
  if last.get('native_rails_search_response')and not last.get('independent_native_lookup'):
   return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Complete independent actual named native lookup unavailable'}
 if c['protocol']['kind']=='any_native_place_search':
  last=timeline.records[-1]if timeline.records else{}
  records=last.get('independent_native_lookup',{}).get('full_records')
  # Wrong/blank documents are genuine negatives. Missing native coverage or
  # transport on an actual result remains unknown, never an agent penalty.
  if (last.get('place',{}).get('results')or last.get('native_rails_search_response'))and(not isinstance(records,list)or not records):
   return {'status':'unknown','reward':None,'checks':{},'reason':'Complete independently identified actual native search results unavailable'}
  records=records or[]
  if not last.get('native_rails_search_response')or not last.get('actual_submitted_query'):records=[]
 if c['protocol']['kind']!='any_native_place_search'and(not isinstance(records,list)or not records):
  return {'status':'unknown','reward':None,'checks':{},'reason':'Complete native place identities unavailable'}
 matched=[]
 for sample in timeline.records[-1:]:
  state=sample.get('place',{})
  if state.get('loading')or state.get('map_async_loading')or state.get('readiness_timeout'):continue
  for record in records:
   kind,number=identity(record)
   proper=(state.get('path')==f'/{kind}/{number}'and bool(state.get('tags'))and any('browse-'+kind in s.split()for s in state.get('sections',[])))
   result=state.get('path')=='/search'and any(public_result_matches(record,row)for row in state.get('results',[]))
   if(proper or result)and native_view_in_place(record,state.get('view',{})):matched.append(record)
 checks={'page_valid':valid_initial_page(terminal,site_origin=site_origin),'actual_native_place_and_map_observed':bool(matched),
         'complete_independent_native_identity_reference':bool(records)}
 if c['protocol']['kind']in('named_place_search','named_place_coordinates'):
  from .map_named_facts_binding import actual_search_checks
  checks.update(actual_search_checks(proof,timeline))
 if c['protocol']['kind']=='named_place_coordinates':
  from lab_generate_skill.admin_query_rules import parse_answer
  from lab_generate_skill.site_query_rules import same_value
  try:v=parse_answer(answer);schema=set(v)=={'latitude','longitude'}
  except(TypeError,ValueError):v={};schema=False
  checks['answer_schema']=schema
  # Task asks a place coordinate; independent geocoder node coordinates are
  # declared before actor execution. No rounding tolerance is invented here.
  checks['requested_coordinates_returned']=any(same_value('decimal',v.get('latitude'),r['lat'])and same_value('decimal',v.get('longitude'),r['lon'])for r in matched)
 success=all(checks.values())
 return {'version':VERSION,'status':'success'if success else'failure','reward':float(success),'checks':checks,'reason':None}


def judge(c,proof,timeline,terminal,answer,*,site_origin):
 kind=c['protocol']['kind']
 if kind in DOCS:return document_judgment(c,proof,timeline,terminal,answer,site_origin=site_origin)
 if kind=='current_view_share':return current_share_judgment(c,proof,timeline,terminal,answer,site_origin=site_origin)
 if kind in('named_place_search','any_native_place_search','named_place_coordinates'):
  return place_judgment(c,proof,timeline,terminal,answer,site_origin=site_origin)
 if kind=='initial_where_is_this':return reverse_judgment(c,proof,timeline,terminal,site_origin=site_origin)
 from . import map_local_view_facts as local_view
 if kind in local_view.KINDS:return local_view.judge(c,proof,timeline,terminal,answer,site_origin=site_origin)
 return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':c['protocol']['missing_predicate']}


def reverse_judgment(c,proof,timeline,terminal,*,site_origin):
 from lab_generate_skill.map_local_capabilities import same_center
 if proof.get('source_binding_sha256')!=fingerprint(source_binding(c)):
  return {'status':'unknown','reward':None,'checks':{},'reason':'Original source binding changed'}
 last=timeline.records[-1]if timeline.records else{};lookup=last.get('independent_native_reverse')
 if last.get('native_rails_reverse_response')and lookup is None:
  return {'status':'unknown','reward':None,'checks':{},'reason':'Full independent actual native reverse response unavailable'}
 checks={'page_valid':valid_initial_page(terminal,site_origin=site_origin),'actual_native_reverse_result_observed':False,
         'original_initial_location_preserved':None,'actual_native_rails_reverse_requested':bool(last.get('native_rails_reverse_response'))}
 if lookup:
  record=lookup['full_record'];kind,number=identity(record);args=lookup['actual_arguments']
  expected=proof.get('initial_view_identity')
  try:
   if expected:
    requested_zoom=int(args['zoom'])if args.get('zoom')not in(None,'')else expected[0]
    checks['original_initial_location_preserved']=same_center(expected,(requested_zoom,float(args['lat']),float(args['lon'])))
  except(ValueError,TypeError,KeyError):pass
  for r in last.get('place',{}).get('results',[]):
   attrs=r.get('attributes',{})
   try:
    good=(r.get('path')==f'/{kind}/{number}'and attrs.get('data-type')==kind and attrs.get('data-id')==str(number)
      and float(attrs['data-lat'])==float(record['lat'])and float(attrs['data-lon'])==float(record['lon'])
      and ' '.join(r.get('text','').split())==' '.join(record['description'].split()))
   except(KeyError,TypeError,ValueError):good=False
   if good:checks['actual_native_reverse_result_observed']=True
 success=all(checks.values());result={'version':VERSION,'status':'success'if success else'failure','reward':float(success),'checks':checks,'reason':None}
 if checks['original_initial_location_preserved']is None:
  result['unevaluated_checks']={'original_initial_location_preserved':
   'No independent native reverse lookup is available to compare the requested location.'if not lookup else
   'The native reverse location arguments or initial reference are unavailable for a valid comparison.'}
 return result


def require_candidate(c,proof):
 """Strict composite source gate; does not reinterpret failed allocations."""
 if(c.get('heldout_quarantine')is not False or proof.get('passed')is not True
     or proof.get('source_binding_sha256')!=fingerprint(source_binding(c))):raise ValueError('Source normal proof changed/failed/heldout')
 cycles=proof.get('cycles')
 if not isinstance(cycles,list)or len(cycles)!=2 or [r.get('cycle')for r in cycles]!=[0,1]:raise ValueError('Two actual independent cycles required')
 factories=set();baselines=[];semantic=[]
 for row in cycles:
  if(not row.get('factory_id')or not row.get('job_identity')or row.get('normal_candidate_passed')is not True
     or row.get('cold_teardown_completed')is not True or row.get('protected_state_unchanged')is not True
     or row.get('clean_reset_verified')is not True or row.get('dirty_reuse_refused')is not True
     or row.get('actor_attempts')!=0 or row.get('api_calls')!=0 or row.get('source_binding_sha256')!=proof['source_binding_sha256']
     or row.get('checks')!=required_controls(c)or not row.get('baseline')or not row.get('reference_semantics_sha256')):
   raise ValueError('Full source/normal controls/baseline/reset/protection/teardown proof required')
  factories.add(row['factory_id']);baselines.append(row['baseline']);semantic.append(row['reference_semantics_sha256'])
 if len(factories)!=2 or baselines[0]!=baselines[1]or semantic[0]!=semantic[1]:raise ValueError('Independent normal factories, baseline, full semantic reference must agree')
 return True


def required_controls(c):
 base={name:True for name in('actual_normal_make_session','original_first_start_preserved','initial_noop_rejected',
       'actual_correct_terminal_passed','wrong_native_object_or_view_rejected',
       '404_rejected','login_rejected','restored_positive_passed','source_full_reference_unchanged')}
 if c['protocol']['kind']in DOCS or c['protocol']['kind']in('current_view_share','named_place_coordinates'):
  base['wrong_answer_rejected']=True
 if c['protocol']['kind']=='current_view_share':base.update(native_artifact_required=True,foreign_artifact_rejected=True,tampered_input_rejected=True)
 if c['protocol']['kind']=='any_native_place_search':base['another_allowed_native_place_passed']=True
 from . import map_local_view_facts as local_view
 if c['protocol']['kind']in local_view.KINDS:base.update(local_view.required_controls(c))
 return base
