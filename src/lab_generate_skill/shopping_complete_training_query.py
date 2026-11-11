"""Private exhaustive native Shopping query scopes; no actor execution strategy."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,json,re
from lab_generate_skill.site_database import select_rows
from lab_generate_skill.site_query_rules import reference_fingerprint,evaluate_query,negative_query_answer
try:
 from .shopping_collection_reference import native_collection
except ImportError:
 from shopping_collection_reference import native_collection
from lab_generate_skill.shopping_search_protection import protected_snapshot
from lab_generate_skill.site_navigation_rules import valid_initial_page

VERSION='shopping-complete-local-training-query-v1';FAMILY='shopping_complete_native_training'
KINDS={'sale_count','slippers_sale','other_kits','plant_milk_prices','lip_max_rating','beauty_max_price','recorded_order_eta'}

def validate(c):
 q=c.get('query',{})
 if c.get('domain')!='shopping'or q.get('family')!=FAMILY or q.get('kind')not in KINDS:raise ValueError('Explicit exhaustive native Shopping query required')
 if c.get('heldout_quarantine')is not False or c.get('eligible_for_training')is not False or c.get('original_evaluation_equivalence')is not False or not c.get('is_explicit_derivative')or c['goal']!=c.get('derived_goal')or not c.get('goal_revision')or not c.get('original_goal'):raise ValueError('Explicit nonheldout deterministic training revision required')
 if not q.get('fields')or c.get('no_external_response_required')is not True:raise ValueError('Typed local completion required')
 return q

def fingerprint(c):return reference_fingerprint({k:v for k,v in c.items()if k!='admission_result'})
def validate_protection(state):
 from lab_generate_skill.shopping_search_protection import TABLES
 tables=set(TABLES)|{'quote','quote_address','quote_payment','sales_order_status_history','review','review_detail','review_store','review_entity_summary','rating_option_vote'}
 if state.get('version')!='shopping-complete-native-query-full-rows-v1'or set(state.get('tables',{}))!=tables or state.get('statement_budget_seconds')!=20:raise ValueError('Exact full native query protection required')
 for row in state['tables'].values():
  if row.get('ignored_columns')!=[]or type(row.get('rows'))is not int or row['rows']<0 or not row.get('primary_key')or not set(row['primary_key'])<=set(row.get('columns',[]))or not re.fullmatch('[0-9a-f]{64}',row.get('sha256','')):raise ValueError('Complete native rows/columns and digest missing')
 return state

def protected_state(site):
 php=Path(__file__).with_name('shopping_complete_query_protection.php');r=site.command(['php','-r',php.read_text().removeprefix('<?php')],capture_output=True,text=True,timeout=240)
 return validate_protection(json.loads(r.stdout))

def account(site,email):
 r=select_rows(site,"SELECT entity_id,group_id FROM customer_entity WHERE email='"+email.replace("'","''")+"'")
 if len(r)!=1:raise ValueError('One native task account required')
 return r[0]


def initialize_order_eta(site,email,c):
 if validate(c)['kind']!='recorded_order_eta':return None
 from os import environ
 if not environ.get('SLURM_JOB_ID')or not environ.get('TMPDIR'):raise RuntimeError('Declared isolated training snapshot required')
 php=Path(__file__).with_name('shopping_recorded_eta.php');s=c['query'];payload={'email':email,'order_number':s['order_number'],'date':s['date'],'operation':'initialize'}
 return json.loads(site.command(['php','-r',php.read_text().removeprefix('<?php'),json.dumps(payload)],capture_output=True,text=True,timeout=120).stdout)


def order_reference(site,email,q):
 php=Path(__file__).with_name('shopping_recorded_eta.php');payload={'email':email,'order_number':q['order_number'],'date':q['date'],'operation':'read'}
 data=json.loads(site.command(['php','-r',php.read_text().removeprefix('<?php'),json.dumps(payload)],capture_output=True,text=True,timeout=120).stdout)
 if not data.get('initialized_native_visible_note')or data.get('external_delivery')is not False:raise ValueError('Declared native customer-visible order note missing')
 return {'object_id':'shopping_order_eta:'+q['order_number'],'values':{'estimated_delivery_date':data['date']},'source_state':data}


def load_catalogue(site,email):
 a=account(site,email);category=select_rows(site,"SELECT DISTINCT entity_id FROM url_rewrite WHERE entity_type='category' AND store_id=1 AND request_path='beauty-personal-care.html'")
 if len(category)!=1:raise ValueError('Unique native Beauty category route required')
 cid=category[0]['entity_id'];scope={'kind':'category','category_id':cid,'path':'/beauty-personal-care.html?product_list_order=price&product_list_dir=desc'}
 first=native_collection(site,scope,email);php=Path(__file__).with_name('shopping_complete_query_catalogue.php');args={'host':urlsplit(site.url).netloc,'group_id':a['group_id'],'category_id':cid}
 from lab_generate_skill.io_utils import atomic_write_json
 from subprocess import CalledProcessError,TimeoutExpired
 import time
 started=time.monotonic()
 def text(value):return value.decode(errors='replace')if isinstance(value,bytes)else value
 try:
  output=site.command(['php','-d','memory_limit=1536M','-r',php.read_text().removeprefix('<?php'),json.dumps(args)],capture_output=True,text=True,timeout=900)
 except(CalledProcessError,TimeoutExpired)as exc:
  atomic_write_json(site.logs/'complete-native-reader-command.json',{'status':'command_failed','exception_type':type(exc).__name__,'returncode':getattr(exc,'returncode',None),'stdout':text(getattr(exc,'stdout',None)),'stderr':text(getattr(exc,'stderr',None)),'elapsed_seconds':time.monotonic()-started,'native_php_sha256':__import__('hashlib').sha256(php.read_bytes()).hexdigest(),'native_category_frontend_first':first,'scope_category_id':cid,'api_calls':0,'actor_attempts':0})
  raise
 atomic_write_json(site.logs/'complete-native-reader-command.json',{'status':'command_completed','returncode':getattr(output,'returncode',0),'stdout':output.stdout,'stderr':getattr(output,'stderr',''),'elapsed_seconds':time.monotonic()-started,'native_php_sha256':__import__('hashlib').sha256(php.read_bytes()).hexdigest(),'native_category_frontend_first':first,'scope_category_id':cid,'api_calls':0,'actor_attempts':0})
 data=json.loads(output.stdout)
 atomic_write_json(site.logs/'complete-native-reader-last.json',{'native_full_catalogue':data,'native_category_frontend_first':first,'scope_category_id':cid})
 if data.get('complete')is not True or type(data.get('total'))is not int or not 0<data['total']==data.get('observed')==data.get('distinct_ids')or data.get('group_id')!=a['group_id']or not data.get('source_hashes'):raise ValueError('Complete native catalogue coverage missing')
 old=0;covered=0;pages=data.get('keyset_pages',[])
 if not pages:raise ValueError('Indexed native coverage evidence missing')
 for i,page in enumerate(pages):
  if page.get('after_id')!=old or type(page.get('rows'))is not int or not 0<=page['rows']<=256 or(page['rows']and page.get('last_id',0)<=old)or(not page['rows']and page.get('last_id')!=old)or(i<len(pages)-1 and page['rows']!=256):raise ValueError('Native keyset has a gap or omitted batch')
  old=page['last_id'];covered+=page['rows']
 if covered!=data['total']or pages[-1]['rows']==256:raise ValueError('Native catalogue end not proven')
 cat=data.get('category',{});beauty=data.get('beauty')
 if cat.get('id')!=cid or cat.get('active')is not True or cat.get('total')!=first['total']or cat.get('distinct_ids')!=first['total']or not isinstance(beauty,list)or len(beauty)!=first['total']or len({r['id']for r in beauty})!=first['total']:raise ValueError('Entire native category count/membership not covered')
 by={r['id']:r for r in beauty}
 for r in first['products']:
  native=by.get(r['id'])
  if native is None or native['name']!=r['name']or Decimal(native['final_price'])!=Decimal(r['price']):raise ValueError('Original native category final prices differ from exhaustive oracle')
 eligible=[r for r in beauty if r.get('salable')is True]
 if not eligible:raise ValueError('Native category has no available maximum candidate')
 maximum=max(Decimal(r['final_price'])for r in eligible);front=[r for r in first['products']if by[r['id']].get('salable')is True]
 if not front or any(Decimal(r['price'])>maximum for r in front)or Decimal(front[0]['price'])!=maximum:raise ValueError('Native price-desc first available product does not show full available category maximum')
 data['native_category_first']=first
 return data


def records(rows,field='price'):
 result=[]
 for r in rows:
  if type(r.get('id'))is not int or r['id']<=0 or not all(isinstance(r.get(k),str)and r[k]for k in('name','sku','url_key')):raise ValueError('Native product identity missing')
  value=r['rating_percent']if field=='rating_percent'else format(Decimal(r['final_price']).normalize(),'f')
  result.append({'name':r['name'],'sku':r['sku'],field:value})
 if len({tuple(sorted(r.items()))for r in result})!=len(result):raise ValueError('Duplicate public product identities')
 return result


def from_catalogue(c,data):
 q=validate(c);kind=q['kind'];common={'full_native_catalogue_record_sha256':data['native_record_sha256'],'total':data['total'],'observed':data['observed'],'distinct_ids':data['distinct_ids'],'group_id':data['group_id'],'source_hashes':data['source_hashes']}
 if kind=='sale_count':values={'on_sale_count':data['salable_on_sale_count']};source=common|{'sale_predicate':'native final_price<regular_price and salable','salable_sale_count':data['salable_on_sale_count']}
 elif kind=='slippers_sale':values={'products':records(data['slippers'])};source=common|{'matches':data['slippers'],'full_scope':'Memory Foam and slippers names, native sale and salable'}
 elif kind=='other_kits':values={'products':records(data['kits'])};source=common|{'matches':data['kits'],'excluded_product_id':104499}
 elif kind=='plant_milk_prices':values={'products':records(data['milks'])};source=common|{'matches':data['milks'],'match_predicate':'milk word and any vegan/almond/oat/soy/coconut word'}
 elif kind=='lip_max_rating':
  if not data['lip']:raise ValueError('No reviewed native lip candidate')
  maximum=max(r['rating_percent']for r in data['lip']);winners=[r for r in data['lip']if r['rating_percent']==maximum]
  answers=[]
  for row in winners:
   if not row.get('approved_reviews')or row['review_count']!=len(row['approved_reviews']):raise ValueError('Full approved native review count differs from visible summary')
   for review in row['approved_reviews']:answers.append({'name':row['name'],'sku':row['sku'],'rating_percent':row['rating_percent'],'review_title':' '.join(review['title'].split()),'review_text':' '.join(review['detail'].split())})
  values={'products':answers};source=common|{'all_reviewed_candidates':data['lip'],'max_rating_percent':maximum,'native_rating_summary_sha256':data['native_rating_summary_sha256'],'native_approved_review_sha256':data['native_approved_review_sha256']}
 elif kind=='beauty_max_price':
  eligible=[r for r in data['beauty']if r.get('salable')is True]
  if not eligible:raise ValueError('No native available Beauty product')
  maximum=max(Decimal(r['final_price'])for r in eligible);winners=[r for r in eligible if Decimal(r['final_price'])==maximum];values={'products':records(winners)};source=common|{'category':data['category'],'all_category_records':data['beauty'],'max_native_final_price':format(maximum.normalize(),'f'),'available_category_count':len(eligible),'complete_native_category_count':len(data['beauty'])}
 else:raise ValueError('Order query requires its native fixture reader')
 return {'object_id':FAMILY+':'+kind,'values':values,'source_state':source}


def initialize_startup(site,email,c):
 validate(c)
 from lab_generate_skill.local_mail_capture import evidence
 assets=getattr(site,'native_static_assets',None);mail=evidence(site.mail_outbox)
 if not assets or mail.get('backend')!='local_sendmail_capture_v1'or mail.get('external_delivery')is not False:raise ValueError('Declared native assets and private local mail profile missing')
 fixture=initialize_order_eta(site,email,c)
 return {'native_static_assets':deepcopy(assets),'local_mail_profile':{'backend':mail['backend'],'external_delivery':False},'order_fixture':fixture}

def reference(site,c,*,catalogue=None,email=None,protection=None):
 q=validate(c)
 if email is None:
  from lab_generate_skill.site_auth import credentials
  email=credentials(site.root,'shopping')['username']
 result=order_reference(site,email,q)if q['kind']=='recorded_order_eta'else from_catalogue(c,catalogue if catalogue is not None else load_catalogue(site,email))
 from lab_generate_skill.local_mail_capture import evidence
 result['source_state']['complete_native_protection']=protected_state(site)if protection is None else deepcopy(protection)
 result['source_state']['native_static_assets']=deepcopy(getattr(site,'native_static_assets',None))
 result['source_state']['local_mail']=evidence(site.mail_outbox)
 if not result['source_state']['native_static_assets']or result['source_state']['local_mail'].get('external_delivery')is not False:raise ValueError('Declared isolated native initial profile missing')
 return result


def require_original_binding(c,original,inventory):
 validate(c)
 if not isinstance(original,dict)or fingerprint(original)!=fingerprint(c):raise ValueError('Exact complete query wave contract required')
 if not isinstance(inventory,dict)or inventory.get('task_id')!=c['source_task_id']or inventory.get('domain')!='shopping'or inventory.get('heldout_quarantine')or inventory.get('goal')!=c['original_goal']or any(inventory.get(k)!=c.get(k)for k in('source_trace_ids','recorded_start_urls')):raise ValueError('Exact original query source required')
 def path(u):
  p=urlsplit(u);return(p.path or'/')+('?' +p.query if p.query else'')+('#'+p.fragment if p.fragment else'')
 starts=list(map(path,inventory['recorded_start_urls']))
 if c.get('recorded_start_paths')!=starts:raise ValueError('Recorded starts differ')
 if c['start_path']!=starts[0]:
  revision=c.get('start_revision',{})
  if revision.get('original_start')!=starts[0]or revision.get('derived_start')!=c['start_path']or revision.get('version')!=1 or not revision.get('reason'):raise ValueError('Explicit query start revision required')
 rev=c['goal_revision']
 if rev.get('original_goal')!=inventory['goal']or rev.get('derived_goal')!=c['goal']or rev.get('version')!=1 or not rev.get('reason'):raise ValueError('Exact goal revision required')

def evaluate(c,page,answer,before,after,*,site_origin,runtime_error=None):
 validate(c);j=evaluate_query(c,page,answer,before,after,site_origin=site_origin,runtime_error=runtime_error);j['version']=VERSION;return j


def expected_controls(c,before):
 from lab_generate_skill.query_record_sets import negative_record_answers,positive_record_answers
 names={'positive':'success','no_answer':'failure','wrong_value':'failure','missing_field':'failure','wrong_object_reference':'failure','404':'failure','login':'failure'}
 names.update(dict.fromkeys(negative_record_answers(c['query'],before['values']),'failure'));names.update(dict.fromkeys(positive_record_answers(c['query'],before['values']),'success'));return names


def require_admission(c,proof):
 validate(c)
 if proof.get('admission_version')!=VERSION or proof.get('contract_fingerprint')!=fingerprint(c)or proof.get('passed')is not True or proof.get('actor_attempts')!=0 or proof.get('api_calls')!=0:raise ValueError('Actual exact complete-native query proof required')
 rows=proof.get('cycles',[])
 if len(rows)!=2 or len({r.get('fresh_instance_id')for r in rows})!=2:raise ValueError('Two actual cold native instances required')
 for r in rows:
  validate_protection(r.get('full_protected_before',{}));validate_protection(r.get('full_protected_after',{}))
  if not re.fullmatch('[0-9a-f]{64}',r.get('fresh_instance_id',''))or r.get('actor_attempts')!=0 or r.get('api_calls')!=0 or not re.fullmatch('[0-9a-f]{64}',r.get('initial_fingerprint',''))or not r.get('public_native_evidence_recorded')or not r.get('fresh_instance_id')or r.get('passed')is not True or r.get('initial_valid')is not True or r.get('checks')!=expected_controls(c,r['initial_reference'])or r.get('initial_reference')!=r.get('final_reference')or not r.get('full_protected_before')or r['full_protected_before']!=r.get('full_protected_after')or r.get('initial_fingerprint')!=r.get('final_fingerprint')or r.get('private_complete_native_oracle_verified')is not True or r.get('normal_startup_verified')is not True or r['initial_reference']['source_state'].get('complete_native_protection')!=r['full_protected_before']:raise ValueError('Native controls/complete oracle/reset incomplete')
 for k in('initial_reference','full_protected_before','initial_fingerprint'):
  if rows[0][k]!=rows[1][k]:raise ValueError('Two cold complete native baselines differ')
 return deepcopy(rows[0]['initial_reference'])
