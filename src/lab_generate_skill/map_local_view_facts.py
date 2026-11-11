"""Actual native pan and named local view artifacts, no external delivery."""
from copy import deepcopy
import json,re
from urllib.parse import parse_qs,urlsplit
from . import map_named_facts_binding as named
from .map_place_identity import native_view_in_place
from .map_frontier_capabilities import native_displaced,native_view
from .map_native_facts_normal import fingerprint,source_binding
from .site_navigation_rules import valid_initial_page

VERSION='map-local-native-view-facts-v1'
KINDS={'native_pan','named_view_geo_uri','named_view_share_link'}

def named_projection(c):
 value=deepcopy(c);value['protocol']['kind']='named_place_search';return value

def validate(c):
 p=c.get('protocol',{});kind=p.get('kind');d=p.get('native_view_declaration')
 if (kind not in KINDS or d!={'version':VERSION,'kind':kind,'original_goal_unchanged':True,
      'original_evaluation_equivalence':False,'external_delivery_required':False}
     or c.get('task_text_changed')is not False or c.get('goal_revision')or c.get('start_revision')
     or p.get('local_finite_interpretation')is not True or p.get('original_model_judge_equivalence_claim')is not False):
  raise ValueError('Exact explicit original native view/local artifact protocol required')
 if kind!='native_pan':named.validate(named_projection(c))
 return d

def require_reference(c,proof):
 validate(c)
 if c['protocol']['kind']!='native_pan':return named.require_reference(named_projection(c),proof)
 initial=proof.get('actual_original_initial_view')
 if (not isinstance(initial,dict)or proof.get('initial_view_identity')!=list(native_view(initial))
     or not initial.get('tiles')or initial.get('map_visible')is not True):
  raise ValueError('Actual original initial native rendered pan reference missing')
 return initial

def initial_signature(view):
 return {'native_geo_uri':view.get('native_geo_uri'),'native_long_link':local(view.get('native_long_link')),
     'map_visible':view.get('map_visible'),'native_zoom':native_view(view)[0]}

def local(url):
 u=urlsplit(url or'');return u.path+('?' +u.query if u.query else'')+('#'+u.fragment if u.fragment else'')

def read(page,kind):
 from .map_view import read_map_view
 from .map_typed_information_share import read_share_state
 from .map_place_page import read_place_page
 row={'view':read_map_view(page)}
 if kind!='native_pan':
  row['place']=read_place_page(page);row['share']=read_share_state(page)
  row['geo_uri_public_control']=page.evaluate("() => {const e=document.querySelector('#geo_uri');return {visible:!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden',href:e?.getAttribute('href')||''};}")
 return row

def same_native_links(view):
 try:
  z,lat,lon=native_view(view);u=urlsplit(view['native_long_link']);parts=parse_qs(u.fragment)['map']
  if len(parts)!=1:return False
  current=parts[0].split('/');return int(current[0])==z and float(current[1])==lat and float(current[2])==lon
 except(ValueError,KeyError,TypeError,IndexError):return False

def judge(c,proof,timeline,terminal,answer,*,site_origin):
 validate(c)
 if proof.get('source_binding_sha256')!=fingerprint(source_binding(c)):
  return {'status':'unknown','reward':None,'checks':{},'reason':'Original native view source changed'}
 last=timeline.records[-1]if timeline.records else{};view=last.get('view',{});kind=c['protocol']['kind']
 if kind!='native_pan'and last.get('native_rails_search_response')and not last.get('independent_native_lookup'):
  return {'version':'full-native-facts-normal-v1','status':'unknown','reward':None,'checks':{},'reason':'Complete independent actual named native lookup unavailable'}
 checks={'page_valid':valid_initial_page(terminal,site_origin=site_origin),'actual_native_view_observed':
     view.get('map_visible')is True and bool(view.get('tiles'))and same_native_links(view)}
 if kind=='native_pan':
  try:checks['native_pan_at_original_zoom']=native_displaced(proof['actual_original_initial_view'],view)
  except(ValueError,KeyError,TypeError):checks['native_pan_at_original_zoom']=False
  checks['original_rendered_native_reference_preserved']=bool(timeline.initial and
    timeline.initial.get('native_initial_view_identity')==proof['initial_view_identity'])
 else:
  checks.update(named.actual_search_checks(proof,timeline))
  records=proof.get('native_records',[]);checks['correct_full_native_named_geography']=len(records)==1 and native_view_in_place(records[0],view)
  state=last.get('share',{});controls=last.get('geo_uri_public_control',{})
  checks['actual_native_share_options_visible']=state.get('visible')is True and state.get('map_visible')is True
  checks['native_original_standard_layer']=state.get('active_base_labels')==state.get('checked_base_labels')==['Standard']and state.get('active_overlay_labels')==[]
  checks['native_inputs_not_tampered']=all(state.get(k+'_visible')is not True or state.get(k+'_value')==state.get(k+'_href')for k in('long','short'))
  try:v=json.loads(answer)if isinstance(answer,str)else answer
  except(ValueError,TypeError):v=None
  field='geo_uri'if kind=='named_view_geo_uri'else'share_link';checks['answer_schema']=isinstance(v,dict)and set(v)=={field}
  if kind=='named_view_geo_uri':
   checks['actual_visible_native_geo_uri_returned']=bool(checks['answer_schema']and controls.get('visible')is True
    and controls.get('href')==view.get('native_geo_uri')and v['geo_uri']==controls.get('href'))
  else:
   from .map_typed_information_share import local_url
   checks['actual_local_native_view_link_returned']=bool(checks['answer_schema']and local_url(v[field],site_origin)
     and v[field]in(state.get('long_href'),state.get('short_href'))and local(state.get('long_href'))==local(view.get('native_long_link')))
 success=all(checks.values())
 return {'version':'full-native-facts-normal-v1','status':'success'if success else'failure','reward':float(success),'checks':checks,'reason':None}

def fields(c):return []if c['protocol']['kind']=='native_pan'else['geo_uri']if c['protocol']['kind']=='named_view_geo_uri'else['share_link']

def public_goal(c):
 validate(c);kind=c['protocol']['kind']
 if kind=='native_pan':return c['goal']+'\nThis local protocol checks a native map pan at its original zoom; changing the zoom alone does not complete the pan.'
 decl=c['protocol']['native_identity_declaration'];region=', '.join(decl['identity_policy']['state'])
 geography='The named place uses the explicitly declared local native geographical interpretation '+decl['query']+', '+region+'.'
 artifact='geo_uri, the actual native Geo URI visible in Share options'if kind=='named_view_geo_uri'else'share_link, an actual native local Share link for the named map view'
 return c['goal']+'\n'+geography+' Finish with a JSON object containing exactly '+artifact+'. This local artifact training protocol returns the link to the user; it does not send messages or require external delivery, and it does not claim equivalence to the original publisher score.'

def required_controls(c):
 if c['protocol']['kind']=='native_pan':return {'wrong_zoom_rejected':True}
 return {'wrong_answer_rejected':True,'foreign_artifact_rejected':True,'tampered_input_rejected':True}
