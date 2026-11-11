"""Recompute native layer predicates from complete original local members."""
import hashlib,json
from pathlib import Path
from urllib.parse import urlsplit
from lab_generate_skill import map_native_layer_completion as layers
from lab_generate_skill.map_local_surface_controls import native_view
from lab_generate_skill.map_native_bbox_reference import compare_database_native_200,compare_database_union
from lab_generate_skill.map_route_normal_capture import exact_pair,complete_route

def require_layer_sample(c,s,terminal):
 directory=Path(s['layer_directory']);responses=[]
 for row in s['layer_notes_responses']:
  if row.get('payload_file'):
   raw=(directory/row['payload_file']).read_bytes()
   if len(raw)!=row['bytes']or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Full original Notes body changed')
   responses.append({'notes_record':row,'notes_body':raw})
 for i,row in enumerate(s['layer_data_transport_records']):
  status=row.get('status')
  if status=='batch_transport_unknown':raise ValueError('Actual full native layer data transport incomplete')
  if status not in ('native_children_complete_adapted_envelope','native_response_unchanged'):continue
  if status=='native_response_unchanged'and row.get('native_original_http_status')!=200:continue
  name=row['envelope']if status=='native_children_complete_adapted_envelope'else row['native_original_body_file']
  raw=(directory/'native-layer-data-transport'/name).read_bytes();bounds=row['requested_bbox_strings']
  db=json.loads((directory/f'layer-final-{i}-full-independent-database.json').read_text())
  if status=='native_children_complete_adapted_envelope':responses.append({'data_transport':row['batch'],'data_body':raw,'data_comparison':compare_database_union(raw,bounds,db)})
  else:responses.append({'data_record':{'url':row['request_url'],'method':'GET','resource_type':'xhr','http_status':200,'content_type':row['native_original_content_type']},'data_body':raw,'data_comparison':compare_database_native_200(raw,bounds,db)})
 if s.get('actual_route_response_body'):
  from lab_generate_skill.map_history_layer_normal import original_bytes
  raw=original_bytes(s['actual_route_response_body']);meta=s['actual_route_response_metadata'];body=json.loads(raw);complete_route(body)
  if hashlib.sha256(raw).hexdigest()!=meta['response_sha256']or len(raw)!=meta['bytes']or body!=s['actual_route_body']or body!=meta['body']or meta['profile']!='car'or not exact_pair(meta['pair'],c['protocol']['original_route_pair'])or meta.get('complete_native_response')is not True:
   raise ValueError('Complete actual original native route request/body changed')
 judgments=[];u=urlsplit(terminal['url']);origin=u.scheme+'://'+u.netloc
 point=None
 try:_,lat,lon=native_view(s['layer_original_initial']);point=[lat,lon]
 except ValueError:pass
 for response in responses or [{}]:
  checks=layers.layer_transition_checks(c['protocol']['completion'],s['layer_initial'],s['layer_surface'],origin,
    original_area_point=point,initial_route=s['layer_initial_route'],terminal_route=s['layer_terminal_route'],require_native_membership=True,**response)
  served=s['layer_served_record'];checks['actual_reviewed_frontend_served']=served is not None if s['layer_surface'].get('map_visible')is True else False
  checks['valid_terminal_document']=type(terminal.get('http_status'))is int and 200<=terminal['http_status']<300 and terminal.get('error_page')is False and terminal.get('login_page')is False
  result={'version':'map-original-local-layer-normal-dispatch-v1','status':'success'if all(v is True for v in checks.values())else'failure','reward':1.0 if all(v is True for v in checks.values())else 0.0,'checks':checks};judgments.append(result)
 expected=next((j for j in reversed(judgments)if j['status']=='success'),judgments[-1])
 if expected['checks']!=s['native_layer_checks']or expected['status']!=s['native_layer_original_judgment']['status']or expected['reward']!=s['native_layer_original_judgment']['reward']:
  raise ValueError('Actual complete native layer predicate failed independent replay')
 if served:
  if served.get('all_four_served')is not True or served.get('actually_loaded_renderer_functions_verified')is not True:raise ValueError('Actual served native layer sources incomplete')
  rows=served['actual_browser_script_responses'];available={}
  for p in directory.glob('served-response-*.json'):
   record=json.loads(p.read_text());raw=p.with_suffix('.js').read_bytes()
   if hashlib.sha256(raw).hexdigest()!=record['sha256']or len(raw)!=record['bytes']:raise ValueError('Actual served native script body changed')
   for name in record['full_reviewed_executable_sources_present']:available[name]=record
  if set(available)!=set(rows):raise ValueError('All actual native served source bodies required')
 return True
