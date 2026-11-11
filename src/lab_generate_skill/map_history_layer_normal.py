"""Finite native History, layer and positive existence predicates.

Missing native coverage is unknown. No bounded search establishes absence.
All private locators retain their original bytes and are consumed before use.
"""
from copy import deepcopy
import hashlib,json,re,math
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
import xml.etree.ElementTree as ET
from .map_native_facts_normal import fingerprint,source_binding,native_raw_read
from .map_place_identity import identity,bounds,native_view_in_place
from .map_native_identity_declarations import declare_query,POLICIES,POLICY_SHA
from .map_route_normal_capture import fingerprint as native_fingerprint

VERSION='map-history-layer-finite-native-v1'
KINDS={'named_history','native_store_exists','local_layer'}
COMMON={'actual_normal_make_session':True,'original_first_start_preserved':True,
 'initial_noop_rejected':True,'actual_correct_terminal_passed':True,
 'wrong_native_object_or_view_rejected':True,'404_rejected':True,'login_rejected':True,
 'restored_positive_passed':True,'source_full_reference_unchanged':True}
NATIVE_FILES={
 'named_history':['app/controllers/changesets_controller.rb','app/assets/javascripts/index/history.js','app/views/changesets/history.html.erb','app/views/changesets/index.html.erb'],
 'native_store_exists':['app/models/node.rb','app/models/way.rb','app/models/relation.rb','app/views/browse/_tag_details.html.erb'],
 'local_layer':['app/controllers/api/map_controller.rb','app/controllers/api/notes_controller.rb','app/models/node.rb','app/models/way.rb','app/models/relation.rb','config/settings.yml','app/assets/javascripts/index.js','app/assets/javascripts/index/browse.js','app/assets/javascripts/index/notes.js','app/assets/javascripts/leaflet.layers.js','vendor/assets/leaflet/leaflet.osm.js']}

def required_controls(c):
 out=deepcopy(COMMON)
 if c['protocol']['kind']=='local_layer':out.update(catalog_only_rejected=True,unchecked_rejected=True,original_route_retained=True)
 if c['protocol']['kind']=='native_store_exists':out.update(wrong_answer_rejected=True,false_absence_rejected=True)
 return out

def locator(p):
 p=Path(p).resolve();return {'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def original_bytes(ref):
 if not isinstance(ref,dict) or set(ref)!={'file','sha256'}:raise ValueError('Exact original private locator required')
 p=Path(ref['file'])
 if not p.is_absolute()or 'actor'in p.parts or not p.is_file():raise ValueError('Original private native member unavailable')
 raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Original private native member bytes changed')
 return raw

def require_http(value):
 if not isinstance(value,dict)or set(value)!={'body','receipt'}:raise ValueError('Full native HTTP body and original receipt required')
 raw=original_bytes(value['body']);receipt=json.loads(original_bytes(value['receipt']))
 u=urlsplit(receipt['requested_url'])
 if (u.scheme!='http'or u.hostname!='127.0.0.1'or u.port is None or u.username or u.password or u.fragment
     or receipt.get('http_status')!=200 or receipt.get('native_only')is not True or receipt.get('external_fallback')is not False
     or receipt.get('complete_transport')is not True or receipt.get('full_body_bytes')!=len(raw)
     or receipt.get('full_body_sha256')!=hashlib.sha256(raw).hexdigest()
     or receipt.get('full_body_file')!=Path(value['body']['file']).name):raise ValueError('Exact complete loopback response required')
 return raw,receipt

def query_reference(query,value):
 raw,receipt=require_http(value);rows=json.loads(raw);q=parse_qs(urlsplit(receipt['requested_url']).query,keep_blank_values=True)
 if urlsplit(receipt['requested_url']).path!='/search'or q!={'q':[query],'format':['jsonv2'],'addressdetails':['1'],'namedetails':['1'],'extratags':['1'],'limit':['50']}:
  raise ValueError('Full independently declared query differs')
 if not isinstance(rows,list)or not rows:raise ValueError('Independent native query coverage unavailable')
 inventory={'status':'full_identity_candidates_require_declaration','full_records':rows,'native_receipt_sha256':native_fingerprint(receipt),'full_native_response_receipt':receipt}
 declaration=declare_query(query,inventory)
 if declaration['status']!='unique_semantic_native_identity_declared':raise ValueError('Independent native query ambiguous')
 matched=[r for r in rows if native_fingerprint(r)==declaration['identity']['full_geocode_sha256']]
 if len(matched)!=1:raise ValueError('Independent full identity changed')
 return matched[0]

HISTORY_SQL="SELECT json_build_object('kind','history','count',count(*)) FROM public.changesets WHERE num_changes > 0 AND min_lon IS NOT NULL AND max_lon IS NOT NULL AND min_lat IS NOT NULL AND max_lat IS NOT NULL;"

def store_sql(name,shop):
 # Values are compiler configuration, never actor input. Complete three-kind
 # matching selection has no LIMIT or selected historical object identifier.
 quote=lambda s:"'"+s.replace("'","''")+"'"
 branches=[]
 for kind in ('node','way','relation'):
  table='current_'+kind+'s';tags='current_'+kind+'_tags';key=kind+'_id'
  branches.append("SELECT '"+kind+"' AS type,o.id,o.version,json_object_agg(t.k,t.v ORDER BY t.k) AS tags FROM public."+tags+" n JOIN public."+tags+" s ON s."+key+"=n."+key+" AND s.k='shop' AND s.v="+quote(shop)+" JOIN public."+table+" o ON o.id=n."+key+" JOIN public."+tags+" t ON t."+key+"=o.id WHERE o.visible=true AND n.k='name' AND n.v="+quote(name)+" GROUP BY o.id,o.version")
 return "SELECT coalesce(json_agg(q ORDER BY q.type,q.id),'[]'::json) FROM ("+' UNION ALL '.join(branches)+') q;'

def require_reference(c,p):
 if p.get('source_binding_sha256')!=fingerprint(source_binding(c))or p.get('two_independent_normal_context_references')is not True:
  raise ValueError('Exact source and two private normal reference contexts required')
 kind=c['protocol']['kind']
 if kind in ('named_history','native_store_exists'):
  query=c['protocol']['query'];native=query_reference(query,p['geography_reference'])
  if p.get('native_records')!=[native]:raise ValueError('Native geography identity differs')
  db=json.loads(original_bytes(p['database_reference']))
  if kind=='named_history':
   if db!={'sql':HISTORY_SQL,'value':{'kind':'history','count':0},'full_native_baseline':p['full_native_baseline']}:
    raise ValueError('Current native geographic History is populated or reference incomplete')
   for ref in p['reference_samples']:
    sample=json.loads(original_bytes(ref));require_history_sample(sample,native)
  else:
   sql=store_sql(c['protocol']['name'],c['protocol']['shop'])
   if db.get('sql')!=sql or db.get('full_native_baseline')!=p['full_native_baseline']or not isinstance(db.get('value'),list):
    raise ValueError('Complete native tag selection missing')
   rows=db['value'];keys=[(r['type'],r['id'])for r in rows]
   if len(keys)!=len(set(keys))or any(r.get('tags',{}).get('name')!=c['protocol']['name']or r['tags'].get('shop')!=c['protocol']['shop']for r in rows):
    raise ValueError('Native candidate tags or complete selection changed')
   if sorted((x['native_record']['osm_type'],x['native_record']['osm_id'])for x in p['store_objects'])!=sorted(keys):
    raise ValueError('Every complete independently selected store object must retain its actual XML and lookup')
   positive=[]
   for item in p['store_objects']:
    raw,receipt=require_http(item['xml_reference']);record=item['native_record'];kind_,number=identity(record)
    if urlsplit(receipt['requested_url']).path!=f'/api/0.6/{kind_}/{number}':raise ValueError('Native object request changed')
    objects=ET.fromstring(raw).findall(kind_)
    if len(objects)!=1 or objects[0].get('id')!=str(number):raise ValueError('Full native object identity changed')
    obj=objects[0];tags={t.get('k'):t.get('v')for t in obj.findall('tag')}
    if len(tags)!=len(obj.findall('tag')):raise ValueError('Duplicate native object tags')
    native_row=[r for r in rows if (r['type'],r['id'])==(kind_,number)]
    if len(native_row)!=1 or tags!=native_row[0]['tags']or str(native_row[0]['version'])!=obj.get('version')or obj.get('visible','true')!='true':raise ValueError('Native DB tags and actual XML differ')
    if kind_=='node':
     from .map_route_normal_capture import point
     if point([obj.get('lat'),obj.get('lon')])!=point([record['lat'],record['lon']]):raise ValueError('Native node coordinates and actual complete lookup differ')
    lr,rr=require_http(item['lookup_reference']);look=json.loads(lr)
    expected={'osm_ids':[{'node':'N','way':'W','relation':'R'}[kind_]+str(number)],'format':['jsonv2'],'addressdetails':['1'],'namedetails':['1'],'extratags':['1']}
    if urlsplit(rr['requested_url']).path!='/lookup'or parse_qs(urlsplit(rr['requested_url']).query)!=expected or look!=[record]:raise ValueError('Actual complete native object lookup differs')
    b=bounds(native);lat,lon=float(record['lat']),float(record['lon']);address=record.get('address',{})
    membership=any(address.get(k)=='Manhattan'for k in ('borough','city_district','suburb'))
    if tags.get('name')==c['protocol']['name']and tags.get('shop')==c['protocol']['shop']and membership and float(b[0])<=lat<=float(b[1])and float(b[2])<=lon<=float(b[3]):positive.append(record)
   if not positive or p.get('positive_store_records')!=positive:raise ValueError('Grounded native snapshot positive existence unavailable; absence remains unknown')
 else:
  from .map_route_normal_capture import complete_route,point
  raw,receipt=require_http(p['route_reference']);body=json.loads(raw);complete_route(body)
  pair=c['protocol']['original_route_pair'];coords=';'.join(str(point(x)[1])+','+str(point(x)[0])for x in pair)
  u=urlsplit(receipt['requested_url'])
  if u.path!='/route/v1/driving/'+coords or parse_qs(u.query)!={'overview':['false'],'geometries':['polyline'],'steps':['true']}or p['route_body']!=body:
   raise ValueError('Full original native car route reference differs')
 if len(p.get('reference_samples',[]))!=2 or len({r['file']for r in p['reference_samples']})!=2:raise ValueError('Two independent actual browser references required')
 for ref in p['reference_samples']:
  sample=json.loads(original_bytes(ref))
  if kind=='local_layer':
   from .history_layer_replay import require_layer_sample
   require_layer_sample(c,sample,sample['reference_terminal'])
   if sample['native_layer_original_judgment']['status']!='success'or sample.get('actual_route_body')!=p['route_body']or sample.get('actual_route_request_verified')is not True:
    raise ValueError('Actual independent original route/layer reference incomplete')
  if kind=='native_store_exists'and not store_sample_matches(p,sample):raise ValueError('Actual private native store inspection reference incomplete')
 sources=p.get('native_source_files');provenance=p.get('native_source_provenance')
 if (not isinstance(sources,list)or not isinstance(provenance,list)or len(sources)!=len(NATIVE_FILES[kind])
     or [v.get('original_native_relative_path')for v in provenance]!=NATIVE_FILES[kind]or len(provenance)!=len(sources)):
  raise ValueError('All actually installed native source bytes and exact provenance required')
 for ref,row in zip(sources,provenance):
  raw=original_bytes(ref)
  if row.get('original_sha256')!=hashlib.sha256(raw).hexdigest()or row.get('copied_raw_file_sha256')!=ref['sha256']:raise ValueError('Original native source copy provenance changed')
 return True

def require_history_sample(sample,native):
 from .map_list_page import list_checks
 state=sample['history'];checks=list_checks({'kind':'history','record_count':0},state)
 if not all(v is True for v in checks.values())or not native_view_in_place(native,sample['view']):raise ValueError('History native geography/list incomplete')
 h=state['history'];feed=urlsplit(h['feed']);expected=parse_qs(feed.query)['bbox']
 matching=[]
 for ref in sample.get('native_history_responses',[]):
  raw,receipt=require_http(ref);u=urlsplit(receipt['requested_url']);q=parse_qs(u.query)
  if u.path=='/history'and q=={'list':['1'],'bbox':expected}and b'No changesets in this area.'in raw and b'<li'not in raw.lower():matching.append(ref)
 if not matching:raise ValueError('Actual native History list request/bbox/full response missing')
 return True

def reference_semantics(p):
 # Original paths/body SHA stay in the private proof. Only invariant semantic
 # values determine equality between two different native leased factories.
 return {k:deepcopy(p[k])for k in ('source_binding_sha256','native_records','positive_store_records','route_body','full_native_baseline')if k in p}

def store_sample_matches(p,sample):
 try:
  state=sample['place'];selected=[r for r in p['positive_store_records']if state['path']=='/'+r['osm_type']+'/'+str(r['osm_id'])]
  if len(selected)!=1:return False
  item=next(x for x in p['store_objects']if x['native_record']==selected[0]);xml,_=require_http(item['xml_reference']);obj=ET.fromstring(xml).find(selected[0]['osm_type'])
  tags=sorted([[t.get('k'),t.get('v')]for t in obj.findall('tag')]);actual=sorted(state['tags'])
  return bool(tags and actual==tags and not state['loading']and not state.get('readiness_timeout')and native_view_in_place(selected[0],state['view']))
 except (ValueError,KeyError,TypeError,StopIteration):return False

def judge(c,p,initial,sample,terminal,answer,*,site_origin):
 checks={'valid_terminal_document':terminal.get('http_status')==200 and terminal.get('login_page')is False and terminal.get('error_page')is False,
  'original_first_start_preserved':initial.get('original_first_start_preserved')is True and initial.get('original_start_path')==c['start_path']}
 try:require_reference(c,p)
 except Exception as error:return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(error)}
 kind=c['protocol']['kind']
 if kind=='named_history':
  checks['requested_native_history_area']=False
  try:require_history_sample(sample,p['native_records'][0]);checks['requested_native_history_area']=urlsplit(terminal['url']).path=='/history'
  except (ValueError,KeyError,TypeError):pass
 elif kind=='native_store_exists':
  checks.update(grounded_native_store_inspected=False,positive_existence_answer=False)
  try:
   value=json.loads(answer)if isinstance(answer,str)else answer
   state=sample['place'];selected=[r for r in p['positive_store_records']if state['path']=='/'+r['osm_type']+'/'+str(r['osm_id'])]
   if len(selected)==1:
    checks['grounded_native_store_inspected']=store_sample_matches(p,sample)
    checks['positive_existence_answer']=isinstance(value,dict)and set(value)=={'exists','object_path'}and value['exists']is True and value['object_path']==state['path']
  except (ValueError,KeyError,TypeError,StopIteration):pass
 else:
  checks.update(sample.get('native_layer_checks',{}));checks['native_layer_terminal_snapshot_bound']=sample.get('layer_surface')==terminal.get('map_native_layer')
  checks['original_full_native_route_body_preserved']=sample.get('actual_route_body')==p['route_body']and bool(sample.get('actual_route_request_verified'))
 passed=bool(checks)and all(v is True for v in checks.values())
 return {'version':VERSION,'status':'success'if passed else'failure','reward':1.0 if passed else 0.0,'checks':checks}
