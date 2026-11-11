"""Candidate search completion; background map style/tiles/center are irrelevant."""
from types import SimpleNamespace
from urllib.parse import urlsplit
from lab_generate_skill.map_place_identity import identity,public_result_matches
from lab_generate_skill.map_named_facts_binding import actual_search_checks,require_actual_lookup
VERSION='eiffel-native-search-result-v190'
SOURCE='b4eecdad9946f2165795'

def evaluate(candidate,*,reference,initial,page,samples,observation_directory,site_origin,search_url,integrity=True,runtime_error=None,search_transport_error=None):
 checks={}
 def result(status,reason):return dict(version=VERSION,status=status,reward={'success':1.,'failure':0.,'unknown':None}[status],checks=dict(checks),reason=reason)
 try:
  if candidate.get('source_task_id')!=SOURCE or candidate.get('validation_scope')!=VERSION or candidate.get('surface')!={'kind':'named_search_result','query':'Eiffel Tower, Paris, France'}:raise ValueError('Exact search-only scope required')
  if integrity is not True or runtime_error or search_transport_error:raise ValueError('Native search transport/runtime/integrity unavailable')
  expected=urlsplit(site_origin);start=urlsplit(site_origin+candidate['start_path'])
  if not isinstance(initial,dict)or initial.get('actor_actions')!=0 or type(initial.get('http_status'))is not int or initial['http_status']!=200 or initial.get('login_page')is not False or initial.get('error_page')is not False or urlsplit(initial.get('url',''))!=start:raise ValueError('Healthy unchanged original page before actions required')
  checks['original_start_verified']=True
  if not isinstance(page,dict)or type(page.get('http_status'))is not int or type(page.get('login_page'))is not bool or type(page.get('error_page'))is not bool or not isinstance(page.get('url'),str):raise ValueError('Complete terminal page evidence required')
  if not 200<=page['http_status']<300 or page['error_page']:raise ValueError('Terminal request/page failed')
  actual=urlsplit(page['url']);checks['healthy_local_page']=(actual.scheme,actual.netloc)==(expected.scheme,expected.netloc)and not page['login_page']
  if not checks['healthy_local_page']:return result('failure','Final page is outside the requested local task.')
  if not samples or any(not isinstance(x,dict)for x in samples)or samples[-1].get('event')!='terminal':raise ValueError('Actual terminal native sample required')
  if identity(reference)!=('way',5013364)or reference.get('extratags',{}).get('wikidata')!='Q243'or reference.get('address',{}).get('city')!='Paris'or reference.get('address',{}).get('country_code')!='fr':raise ValueError('Independently declared Paris Eiffel identity differs')
  last=samples[-1];state=last.get('place')
  if not isinstance(state,dict)or any(k not in state for k in ('path','results','tags','sections','loading'))or type(state['loading'])is not bool:raise ValueError('Native result/detail evidence missing')
  if state['loading']:raise ValueError('Native result is still loading')
  if state['path']!=actual.path:raise ValueError('Terminal page and native result disagree')
  kind,number=identity(reference)
  found=state['path']=='/search'and any(public_result_matches(reference,r)and bool(r.get('text','').strip())for r in state['results'])
  detail=state['path']==f'/{kind}/{number}'and bool(state['tags'])and any('browse-'+kind in s.split()for s in state['sections'])
  checks['requested_native_result_visible']=bool(found or detail)
  lookup=last.get('independent_native_lookup');request=last.get('native_rails_search_response')
  if (found or detail)and not(request and lookup):raise ValueError('Visible target lacks actual search and independent lookup evidence')
  if request:
   u=urlsplit(request['url'])
   if(u.scheme,u.netloc)!=(expected.scheme,expected.netloc):raise ValueError('Search request came from another website')
  if lookup:
   require_actual_lookup(last,observation_directory)
   u=urlsplit(lookup['requested_url']);s=urlsplit(search_url)
   if(u.scheme,u.netloc)!=(s.scheme,s.netloc):raise ValueError('Observed-object lookup used another native service')
  checks.update(actual_search_checks({'native_records':[reference]},SimpleNamespace(records=samples)))
  return result('success'if all(checks.values())else'failure','Requested native search result is the completion boundary.')
 except (ValueError,KeyError,TypeError,OSError,AttributeError)as exc:return result('unknown',str(exc))
