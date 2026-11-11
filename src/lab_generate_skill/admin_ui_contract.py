"""Observable UI predicates and request receipts; no prescribed actor actions."""
import json,re
from urllib.parse import urlsplit

def install(page,binding):
 spec=binding['spec'];page._admin_ui_spec=spec;page._admin_completed_requests=[]
 from .admin_category_operations import install as install_category
 install_category(page,binding)
 from .admin_grid_operation import install as install_grid_operation
 install_grid_operation(page,binding)
 if spec.get('required_listing_scope'):
  from .admin_listing_scope import install as install_listing
  install_listing(page,binding)
 if spec.get('required_request_path'):
  def response_seen(response):
   if urlsplit(response.url).path.rstrip('/')==spec['required_request_path'].rstrip('/') and response.request.method==spec.get('request_method','POST') and 200<=response.status<400:
    page._admin_completed_requests.append({'path':urlsplit(response.url).path,'status':response.status,'method':response.request.method})
  page.on('response',response_seen)

def probe(page):
 spec=getattr(page,'_admin_ui_spec',{});values={};errors={}
 for key,field in spec.get('ui_fields',{}).items():
  loc=page.locator(field['selector']);read=field.get('read','text')
  try:
   if read=='list_text':values[key]=[' '.join(e.inner_text().split()) for e in loc.all() if e.is_visible()];continue
   if read=='visible':values[key]=any(e.is_visible() for e in loc.all());continue
   if loc.count()!=1:raise ValueError('missing_or_ambiguous_element')
   if read=='value':values[key]=loc.input_value()
   elif read=='text':values[key]=' '.join(loc.inner_text().split())
   elif read=='number':values[key]=re.sub(r'[^0-9.-]','',loc.inner_text())
   elif read=='attribute':values[key]=loc.get_attribute(field['attribute'])
   else:raise ValueError('unsupported_observable')
  except Exception as exc:errors[key]=type(exc).__name__+': '+str(exc).split('\n')[0]
 from .admin_grid_operation import probe as probe_grid_operation
 from .admin_listing_scope import probe as probe_listing
 listing=probe_listing(page,spec['required_listing_scope']) if spec.get('required_listing_scope') else None
 return {'values':values,'errors':errors,'completed_requests':getattr(page,'_admin_completed_requests',[]),
         'grid_operation':probe_grid_operation(page), **({'unfiltered_listing':listing} if spec.get('required_listing_scope') else {})}

def checks(binding,before,after,page,answer):
 spec=binding['spec'];state=page.get('ui_contract',{});values=state.get('values',{});result={'observations_available':not state.get('errors'),'records_unchanged':before['records']==after['records']}
 if spec.get('required_request_path'):result['operation_request_completed']=bool(state.get('completed_requests'))
 if spec['mode']=='ui_query':
  from .admin_query_rules import parse_answer
  from .admin_contract_rules import equivalent
  try:got=parse_answer(answer)
  except (ValueError,TypeError):got={}
  ref=binding.get('query_reference',{});result['answer_schema']=bool(ref) and set(got)==set(ref)
  result['display_unchanged']=values==ref
  for key,value in ref.items():result['answer_'+key]=equivalent('price' if spec['ui_fields'][key].get('read')=='number' else key,got.get(key),value)
 else:
  for key,value in spec.get('ui_expected',{}).items():result['observed_'+key]=values.get(key)==value
  if spec.get('restore_default_columns'):result['default_columns_restored']=bool(binding.get('default_columns')) and values.get('columns')==binding['default_columns']
  if not spec.get('ui_expected') and not spec.get('required_request_path') and not spec.get('restore_default_columns'):raise ValueError('empty_ui_contract')
 if spec.get('required_final_path'):result['correct_page']=urlsplit(page['url']).path.rstrip('/')==spec['required_final_path'].rstrip('/')
 return result
