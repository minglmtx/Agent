"""Candidate terminal-only checks for four native operations; no admission grant."""
from decimal import Decimal,InvalidOperation
from urllib.parse import urlsplit
VERSION='admin-native-mutation4-candidate-v1'
COPY_FIELDS=('name','price','description','short_description','tax_class_id','visibility')
def only(rows):
 if len(rows)!=1:raise ValueError('missing_or_ambiguous_object')
 return rows[0]
def number(v):
 if isinstance(v,bool)or v is None:raise ValueError('invalid_number')
 x=Decimal(str(v))
 if not x.is_finite():raise ValueError('nonfinite_number')
 return x
def equal_rows_except(before,after,key,exclude):
 return {str(r[key]):r for r in before if str(r[key])not in exclude}=={str(r[key]):r for r in after if str(r[key])not in exclude}
def evaluate(contract,before,after,page,origin,runtime_error=None):
 result=dict(version=VERSION,status='unknown',reward=None,checks={})
 if runtime_error:return dict(result,reason='runtime_error')
 try:
  for payload in (before,after):
   if payload['base'].get('records_error')or payload['base'].get('record_errors'):raise ValueError('base_capture_error')
   assert isinstance(payload['native'],dict)
  if not isinstance(page['login'],bool)or not isinstance(page['page_error'],bool):raise ValueError('invalid_page_evidence')
  checks=result['checks'];u=urlsplit(page['url']);o=urlsplit(origin)
  checks['correct_local_site']=(u.scheme,u.netloc)==(o.scheme,o.netloc)
  checks['valid_authenticated_page']=not(page['login']or page['page_error'])
  kind=contract['operation']
  if kind in ('theme_schedule','synonym_create'):
   entity,key=('design','design_change_id')if kind=='theme_schedule'else('synonyms','group_id')
   old=before['native'][entity];new=after['native'][entity];ids={str(r[key])for r in old};added=[r for r in new if str(r[key])not in ids]
   checks['one_new_record']=len(added)==1
   checks['existing_records_unchanged']=equal_rows_except(old,new,key,{str(r[key])for r in added})
   if kind=='theme_schedule':
    theme=only([r for r in before['native']['themes']if r['theme_title']==contract['theme']and r['area']=='frontend'])
    checks['saved_requested_schedule']=len(added)==1 and str(added[0]['store_id'])==contract['store_id']and str(added[0]['design'])==str(theme['theme_id'])and added[0]['date_from']==contract['date_from']and added[0]['date_to']==contract['date_to']
   else:
    terms=[s.strip().casefold()for s in added[0]['synonyms'].split(',')]if len(added)==1 else[]
    checks['saved_requested_terms_scope']=len(added)==1 and sorted(terms)==sorted(contract['terms'])and str(added[0]['store_id'])==contract['store_id']and str(added[0]['website_id'])==contract['website_id']
  elif kind in ('stock_threshold','duplicate_product'):
   old=before['base']['records']['product'];new=after['base']['records']['product']
   source=only([r for r in old if r['sku']==contract['source_sku']]);existing=only([r for r in new if str(r['entity_id'])==str(source['entity_id'])])
   if kind=='stock_threshold':
    original=only([r for r in before['native']['stock']if str(r['product_id'])==str(source['entity_id'])])
    current=only([r for r in after['native']['stock']if str(r['item_id'])==str(original['item_id'])])
    checks['same_stock_object']=str(current['product_id'])==str(source['entity_id'])and str(current['stock_id'])==str(original['stock_id'])
    value=current['notify_stock_qty'];inherit=str(current['use_config_notify_stock_qty'])
    if inherit not in ('0','1'):raise ValueError('invalid_inheritance_flag')
    # NULL is a captured SQL value, distinct from an absent evidence key.
    checks['effective_saved_threshold']=inherit=='0'and value is not None and number(value)==number(contract['threshold'])
    checks['other_stock_unchanged']=equal_rows_except(before['native']['stock'],after['native']['stock'],'item_id',{str(original['item_id'])})
    checks['other_products_unchanged']=equal_rows_except(old,new,'entity_id',{str(source['entity_id'])})
   else:
    ids={str(r['entity_id'])for r in old};added=[r for r in new if str(r['entity_id'])not in ids]
    checks['one_new_product']=len(added)==1
    checks['different_unique_sku']=len(added)==1 and bool(str(added[0]['sku']).strip())and added[0]['sku']!=source['sku']and sum(r['sku']==added[0]['sku']for r in new)==1
    checks['copied_source_fields']=len(added)==1 and all(added[0].get(f)==source.get(f)for f in COPY_FIELDS)
    checks['original_identity_and_content_preserved']=existing['sku']==source['sku']and all(existing.get(f)==source.get(f)for f in COPY_FIELDS)
    checks['other_products_unchanged']=equal_rows_except(old,new,'entity_id',{str(source['entity_id']),*[str(r['entity_id'])for r in added]})
  else:raise ValueError('unsupported_operation')
  result.update(status='success'if all(checks.values())else'failure',reward=int(all(checks.values())))
 except (KeyError,TypeError,ValueError,InvalidOperation,AssertionError)as exc:result.update(status='unknown',reward=None,reason=type(exc).__name__+':'+str(exc))
 return result
