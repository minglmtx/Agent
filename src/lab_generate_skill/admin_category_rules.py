"""Strict private predicates for native category positions and applied SKU search."""
from copy import deepcopy
from urllib.parse import urlsplit,parse_qs,unquote
import base64,re
SOURCES=('65d44f1f647a37cce37a','b3948d69b63665617e41')

def identity(state):
 if not isinstance(state,dict)or state.get('record_errors'):raise ValueError('complete_native_state_required')
 records=state['records']
 if not all(isinstance(records.get(k),list)for k in('product','category','category_product')):raise ValueError('complete_native_records_required')
 cats=[r for r in records['category']if r.get('name')=='New Category Name'];products={}
 if len(cats)!=1:raise ValueError('unique_category_required')
 for sku,name in [('WSH12','Erika Running Short'),('WT07','Maya Tunic')]:
  rows=[r for r in records['product']if r['sku']==sku and r['name']==name]
  if len(rows)!=1:raise ValueError('unique_product_required')
  products[sku]=str(rows[0]['entity_id'])
 return str(cats[0]['entity_id']),products

def edge(state,category,product):
 rows=[r for r in state['records']['category_product']if str(r['category_id'])==category and str(r['product_id'])==product]
 if len(rows)!=1:raise ValueError('unique_declared_category_membership_required')
 return rows[0]

def position_judgment(before,after,runtime_error=None):
 if runtime_error:return dict(status='unknown',reward=None,error='runtime_error')
 try:
  cat,products=identity(before);assert identity(after)==(cat,products)
  initial=edge(before,cat,products['WSH12']);actual=edge(after,cat,products['WSH12']);assert int(initial['position'])==0
  normalized=deepcopy(after);target=edge(normalized,cat,products['WSH12']);target['position']=initial['position']
  oldcat=next(r for r in before['records']['category']if str(r['entity_id'])==cat)
  newcat=next(r for r in normalized['records']['category']if str(r['entity_id'])==cat)
  # Native Save materializes these previously absent, empty optional fields.
  # Only absent-to-null on the selected category is permitted.
  for key in ('custom_design','meta_title','description','meta_description'):
   if key not in oldcat and newcat.get(key,'not_null') is None:newcat.pop(key)
  checks=dict(target_position_saved=int(actual['position'])==10,unrelated_declared_state_unchanged=normalized==before)
 except (KeyError,TypeError,ValueError,AssertionError):return dict(status='unknown',reward=None,error='incomplete_or_inconsistent_native_state')
 return dict(status='success'if all(checks.values())else'failure',reward=1.0 if all(checks.values())else 0.0,checks=checks,error=None)

def request_filter(url,post_data,origin):
 u=urlsplit(url)
 if u.netloc!=urlsplit(origin).netloc:return None
 # Native category grid is an HTML AJAX response, not the uiRegistry provider.
 prefix='/admin/catalog/category/grid/'
 if not u.path.startswith(prefix):return None
 pieces=u.path[len(prefix):].strip('/').split('/')
 if len(pieces)%2:raise ValueError('malformed_native_grid_route')
 params={}
 for k,v in zip(pieces[::2],pieces[1::2]):
  k,v=unquote(k),unquote(v)
  if k in params:raise ValueError('duplicate_native_route_parameter')
  params[k]=[v]
 for incoming in (parse_qs(u.query,keep_blank_values=True),parse_qs(post_data or '',keep_blank_values=True)):
  for k,v in incoming.items():
   if k in params and params[k]!=v:raise ValueError('conflicting_native_grid_parameters')
   params[k]=v
 category=params.get('id')
 if not category or len(category)!=1 or not re.fullmatch(r'[0-9]+',category[0]):raise ValueError('native_category_identity_missing')
 encoded=params.get('filter')
 if encoded is None:return dict(category_id=category[0],filters={},filter_supplied=False)
 if len(encoded)!=1:raise ValueError('ambiguous_native_filter')
 try:decoded=base64.b64decode(encoded[0],validate=True).decode('utf-8')
 except (ValueError,UnicodeError):raise ValueError('invalid_native_filter_encoding')
 fields=parse_qs(decoded,keep_blank_values=True)
 if any(len(v)!=1 for v in fields.values()):raise ValueError('ambiguous_native_filter_fields')
 return dict(category_id=category[0],filters={k:v[0]for k,v in fields.items()},filter_supplied=True)

def query_judgment(state,view,receipts,runtime_error=None):
 if runtime_error:return dict(status='unknown',reward=None,error='runtime_error')
 try:
  cat,products=identity(state);edge(state,cat,products['WSH12'])
  if not isinstance(view,dict)or view.get('capture_error'):raise ValueError('view_missing')
  required=('category_id','sku_filter','membership_filter','rows','complete','page_valid')
  if not all(k in view for k in required):raise ValueError('view_incomplete')
  if not isinstance(receipts,list):raise ValueError('receipt_list_missing')
  last=receipts[-1]if receipts else None
  if last and last.get('error'):raise ValueError('request_capture_error')
  if last and not last.get('response_valid'):raise ValueError('native_grid_response_invalid')
  checks=dict(correct_category=str(view['category_id'])==cat,page_valid=view['page_valid']is True,complete_native_grid=view['complete']is True,visible_sku_filter=view['sku_filter']=='WSH12',membership_scope=view['membership_filter']=='1',exact_matching_rows=[r['sku']for r in view['rows']]==['WSH12']and[str(r['id'])for r in view['rows']]==[products['WSH12']],response_matches_visible_rows=bool(last and last.get('rows')==view['rows']),native_filter_applied=bool(last and last['category_id']==cat and last['filters'].get('sku')=='WSH12'and last['filters'].get('in_category')=='1'))
 except (KeyError,TypeError,ValueError):return dict(status='unknown',reward=None,error='missing_or_invalid_native_evidence')
 return dict(status='success'if all(checks.values())else'failure',reward=1.0 if all(checks.values())else 0.0,checks=checks,error=None)
