"""Versioned local training fixtures and independent completion conditions.

This module is a candidate, not installed in the production actor runtime.
Native checkout/offline transport is retained. It never generates actor actions.
"""
import copy,hashlib,json,re
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from datetime import datetime
from lab_generate_skill.site_navigation_rules import valid_initial_page
from lab_generate_skill.site_query_rules import reference_fingerprint

VERSION='shopping-offline-training-v1';ADMISSION_VERSION='shopping-offline-training-two-cold-v1'
MODES={'shipping','payment','billing','coupon','quantity','contact','review'}
ADDRESS_FIELDS=('firstname','lastname','street','city','country_id','region_id','region','postcode','telephone')
TASK_ITEM_FIELDS={'updated_at','qty','row_total','base_row_total','row_total_with_discount','tax_amount','base_tax_amount','tax_percent','row_total_incl_tax','base_row_total_incl_tax','row_weight','free_shipping','discount_amount','base_discount_amount','discount_percent','applied_rule_ids','discount_tax_compensation_amount','base_discount_tax_compensation_amount','tax_before_discount','base_tax_before_discount'}
HEADER_IDENTITY=('entity_id','customer_id','store_id','is_active','is_virtual','customer_email','customer_group_id')

def validate(c):
 s=c.get('offline_training',{});mode=s.get('mode')
 if c.get('domain')!='shopping'or mode not in MODES:raise ValueError('Supported Shopping training mode required')
 if c.get('task_id')==c.get('source_task_id')or not c.get('is_explicit_derivative')or c.get('original_evaluation_equivalence')is not False or c.get('heldout_quarantine')or c.get('eligible_for_training'):raise ValueError('Explicit separated development training derivative required')
 if not c.get('original_goal')or c.get('goal')!=c.get('derived_goal')or c.get('task_text_changed')!=(c['goal']!=c['original_goal']):raise ValueError('Exact original goal and revision required')
 if s.get('fixture_version')!='native-offline-checkout-and-local-mail-v1':raise ValueError('Explicit native fixture version required')
 if mode in ('shipping','payment')and not all(isinstance(s.get(k),str)and s[k]for k in ('initial_method','desired_method')):raise ValueError('Explicit initial and requested method required')
 if mode in ('shipping','payment')and s['initial_method']==s['desired_method']:raise ValueError('Change target already initially satisfied')
 if mode=='coupon'and(s.get('code')!='SAVE10'or s.get('percent')!=10):raise ValueError('Reviewed exact native local coupon fixture required')
 if mode=='billing'and set(s.get('address',{}))!=set(ADDRESS_FIELDS):raise ValueError('Complete billing fields required')
 if s.get('native_billing_shipping_touch')is not None and(mode!='billing'or s['native_billing_shipping_touch']!='owned-original-shipping-updated-at-v1'):raise ValueError('Exact billing-only native clock permission required')
 if mode=='quantity'and(type(s.get('product_id'))is not int or s['product_id']<=0 or s.get('initial_quantity')!=1 or s.get('quantity')!=2):raise ValueError('Explicit initialized target and quantities required')
 if mode=='contact'and(set(s.get('form',{}))!={'name','email','telephone','comment'}or not all(isinstance(v,str)and v for v in s['form'].values())):raise ValueError('Exact local contact form target required')
 if mode=='review'and(type(s.get('product_id'))is not int or s['product_id']<=0 or s.get('stars')not in range(1,6)or not all(isinstance(s.get(k),str)and s[k]for k in ('title','detail','nickname'))):raise ValueError('Explicit product/rating/full text required')
 return s

def fingerprint(c):return reference_fingerprint({k:c.get(k)for k in ('task_id','source_task_id','domain','goal','original_goal','derived_goal','start_path','recorded_start_urls','source_trace_ids','offline_training','goal_revision','start_revision','initial_state_revision','heldout_quarantine')})
def amount(v):
 if isinstance(v,bool):raise ValueError('Invalid money')
 x=Decimal(str(v))
 if not x.is_finite():raise ValueError('Nonfinite money')
 return x

def row_by_type(rows,kind):
 r=[v for v in rows if v['address_type']==kind]
 if len(r)!=1:raise ValueError('Unique native quote address required')
 return r[0]

def unchanged_billing_shipping(initial,current,s):
 before=row_by_type(initial['addresses'],'shipping');after=row_by_type(current['addresses'],'shipping')
 if s.get('native_billing_shipping_touch')!='owned-original-shipping-updated-at-v1':return before==after
 # Native billing save touches this original owned shipping row. Every other
 # column, its PK, quote owner and row set retain exact original values.
 if set(before)!=set(after)or set(before)<={'updated_at'}or any(k not in before for k in ('address_id','quote_id','customer_id','updated_at')):return False
 if len(initial['addresses'])!=2 or len(current['addresses'])!=2 or {r['address_type']for r in initial['addresses']}!={'shipping','billing'}or {r['address_type']for r in current['addresses']}!={'shipping','billing'}:return False
 # The declared target billing address may be natively replaced; its quote
 # and account remain bound. The non-target shipping PK may never change.
 if any(r['quote_id']!=current['quote_id']or r['customer_id']!=current['customer_id']for r in current['addresses']):return False
 if before['quote_id']!=initial['quote_id']or after['quote_id']!=current['quote_id']or before['customer_id']!=initial['customer_id']or after['customer_id']!=current['customer_id']:return False
 for clock in (before['updated_at'],after['updated_at']):
  if not isinstance(clock,str)or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}',clock):return False
 try:
  if datetime.strptime(after['updated_at'],'%Y-%m-%d %H:%M:%S')<datetime.strptime(before['updated_at'],'%Y-%m-%d %H:%M:%S'):return False
 except ValueError:return False
 return {k:v for k,v in before.items()if k!='updated_at'}=={k:v for k,v in after.items()if k!='updated_at'}


def unchanged_cart(initial,current,mode,s):
 old={r['item_id']:r for r in initial['items']};new={r['item_id']:r for r in current['items']}
 if set(old)!=set(new)or initial['options']!=current['options']:return False
 for ident,row in old.items():
  target=mode=='quantity'and row['product_id']==s['product_id'];allowed=TASK_ITEM_FIELDS if target else ({'updated_at','discount_amount','base_discount_amount','discount_percent','applied_rule_ids','discount_tax_compensation_amount','base_discount_tax_compensation_amount','row_total_with_discount'}if mode=='coupon'else{'updated_at'})
  if {k:v for k,v in row.items()if k not in allowed}!={k:v for k,v in new[ident].items()if k not in allowed}:return False
 return True

def evaluate(c,page,initial,current,*,site_origin,ui=None,runtime_error=None):
 s=validate(c);mode=s['mode']
 def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
 if runtime_error:return unknown('Runtime error prevented terminal observation')
 if not isinstance(page,dict)or type(page.get('http_status'))is not int or not 200<=page['http_status']<500:return unknown('Terminal page unavailable')
 if not isinstance(initial,dict)or not isinstance(current,dict):return unknown('Native initialized quote/account baseline missing')
 if mode in ('contact','review'):raise ValueError('Use independent mail/review evaluator for this mode')
 try:
  b,a=initial['header'],current['header'];checks={'page_valid':valid_initial_page(page,site_origin=site_origin),'original_quote_identity_and_active':initial['quote_id']==current['quote_id']==a['entity_id']and initial['customer_id']==current['customer_id']==a['customer_id']and all(b.get(k)==a.get(k)for k in HEADER_IDENTITY)and a['is_active']==1,'other_accounts_orders_and_profiles_unchanged':initial['foreign_protected']==current['foreign_protected'],'native_offline_configuration_unchanged':initial['configuration']==current['configuration'],'original_cart_products_options_unchanged':unchanged_cart(initial,current,mode,s)}
  if mode=='shipping':
   before=row_by_type(initial['addresses'],'shipping');after=row_by_type(current['addresses'],'shipping')
   checks.update(initial_shipping_method_bound=before['shipping_method']==s['initial_method'],requested_shipping_method_saved=after['shipping_method']==s['desired_method'],original_shipping_address_unchanged=all(before[k]==after[k]for k in ADDRESS_FIELDS),billing_address_unchanged=row_by_type(initial['addresses'],'billing')==row_by_type(current['addresses'],'billing'),coupon_unchanged=b.get('coupon_code')==a.get('coupon_code'))
  elif mode=='payment':
   if not isinstance(ui,dict)or not isinstance(ui.get('payment_methods'),list):return unknown('Current native payment controls were not captured')
   methods=ui['payment_methods'];checked=[r['value']for r in methods if r.get('checked')]
   checks.update(native_payment_method_selected=checked==[s['desired_method']],native_alternative_available={s['initial_method'],s['desired_method']}<=set(r['value']for r in methods),native_quote_visible=str(ui.get('quote_id'))==str(initial['quote_id'])and str(ui.get('customer_id'))==str(initial['customer_id']),quote_addresses_unchanged=initial['addresses']==current['addresses'],coupon_unchanged=b.get('coupon_code')==a.get('coupon_code'))
  elif mode=='billing':
   billing=row_by_type(current['addresses'],'billing');shipping=row_by_type(current['addresses'],'shipping')
   checks.update(requested_billing_address_saved=all(str(billing.get(k)or'')==str(v)for k,v in s['address'].items()),billing_differs_from_shipping=any(billing[k]!=shipping[k]for k in ADDRESS_FIELDS),original_shipping_unchanged=unchanged_billing_shipping(initial,current,s),coupon_unchanged=b.get('coupon_code')==a.get('coupon_code'))
  elif mode=='coupon':
   subtotal=amount(b['subtotal']);discount=(subtotal*Decimal(s['percent'])/100).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);reduction=amount(a['subtotal'])-amount(a['subtotal_with_discount'])
   checks.update(requested_coupon_saved=a.get('coupon_code')==s['code'],native_item_subtotal_unchanged=amount(a['subtotal'])==subtotal,native_percent_discount_applied=subtotal>0 and abs(reduction-discount)<=Decimal('.01'),native_discount_reduced_total=amount(a['grand_total'])<amount(b['grand_total']))
  else:
   targets=[r for r in current['items']if r['product_id']==s['product_id']];before=[r for r in initial['items']if r['product_id']==s['product_id']]
   checks.update(native_initial_quantity_bound=len(before)==1 and amount(before[0]['qty'])==s['initial_quantity'],requested_quantity_saved=len(targets)==1 and amount(targets[0]['qty'])==s['quantity'],coupon_unchanged=b.get('coupon_code')==a.get('coupon_code'))
 except(KeyError,TypeError,ValueError,ArithmeticError):return unknown('Incomplete native terminal quote or condition capture')
 passed=all(checks.values());return {'version':VERSION,'status':'success'if passed else'failure','reward':float(passed),'checks':checks,'reason':None}

def expected_controls(c):
 mode=validate(c)['mode'];names=['no_op','filled_unsaved','wrong_target','wrong_account_reference','wrong_quote_reference','404','login']
 if mode=='payment':names=['no_op','same_method','wrong_target','wrong_account_reference','wrong_quote_reference','404','login']
 if mode=='coupon':names+=['invalid_code']
 if mode=='review':names=['no_op','filled_unsaved','wrong_product','wrong_rating','wrong_title','wrong_detail','wrong_author_reference','404','login']
 if mode=='contact':names=['no_op','filled_unsaved','invalid_form','wrong_comment','wrong_email','404','login']
 return dict.fromkeys(names,'failure')|{'positive':'success','saved_then_home':'success'} if mode!='payment'else dict.fromkeys(names,'failure')|{'positive':'success'}

def require_admission(c,proof):
 validate(c)
 if proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c)or proof.get('passed')is not True or proof.get('api_calls')!=0 or proof.get('actor_attempts')!=0:raise ValueError('Exact valid native two-cold training proof required')
 rows=proof.get('cycles',[])
 if len(rows)!=2:raise ValueError('Two cold cycles required')
 cold=[r.get('cold_instance_id')for r in rows]
 if any(not isinstance(x,str)or not re.fullmatch('[0-9a-f]{64}',x)for x in cold)or len(set(cold))!=2 or any(r.get('cold_instance')is not True or r.get('normal_startup_verified')is not True for r in rows):raise ValueError('Two distinct actual cold profiles required')
 for r in rows:
  if r.get('checks')!=expected_controls(c)or r.get('passed')is not True or r.get('initial_valid')is not True or r.get('full_protected_before')!=r.get('full_protected_after')or not r.get('full_protected_before')or r.get('restored')is not True or r.get('initial_state')!=r.get('final_state')or not r.get('initial_fingerprint')or r['initial_fingerprint']!=r.get('final_fingerprint'):raise ValueError('Actual controls or complete restoration failed')
 if c.get('initial_state_revision',{}).get('native_static_publication'):
  for r in rows:
   assets=r.get('native_static_assets',{});module=assets.get('Magento_OfflinePayments',{})
   if set(assets)!={'Magento_OfflinePayments'}or module.get('native_bytes_only')is not True or module.get('original_published_bytes_unchanged')is not True or module.get('external_source_used')is not False or not module.get('original_published_sha256')or not module.get('added_installed_sha256'):raise ValueError('Actual installed native asset provenance missing')
  if rows[0]['native_static_assets']!=rows[1]['native_static_assets']:raise ValueError('Native asset source differs across cold instances')
 if c.get('initial_state_revision',{}).get('native_checkout_stage'):
  try:
   from . import shopping_native_payment_initial as payment_initial
  except ImportError:
   import shopping_native_payment_initial as payment_initial
  for row in rows:payment_initial.validate_evidence(c,row)
  if rows[0]['native_payment_stage']['native_checkout_storage']!=rows[1]['native_payment_stage']['native_checkout_storage']:raise ValueError('Two native initial client selections differ')
 if rows[0]['initial_state']!=rows[1]['initial_state']or rows[0]['full_protected_before']!=rows[1]['full_protected_before']or rows[0]['initial_fingerprint']!=rows[1]['initial_fingerprint']:raise ValueError('Independent prepared cold baselines differ')

def state(site,email):
 return native_command(site,{'operation':'read','email':email,'strict_payment_stage':bool(getattr(site,'native_payment_stage',None))})

def native_command(site,payload):
 php=Path(__file__).with_name('shopping_offline_training.php');return json.loads(site.command(['php','-d','memory_limit=1024M','-r',php.read_text().removeprefix('<?php'),json.dumps(payload)],capture_output=True,text=True,timeout=240).stdout)

def prepare_fixture(site,email,c):
 validate(c)
 if not __import__('os').environ.get('SLURM_JOB_ID')or not __import__('os').environ.get('TMPDIR'):raise RuntimeError('Private isolated native allocation required')
 return native_command(site,{'operation':'prepare','email':email,'spec':c['offline_training']})

def restore_selected_quote(site,baseline):
 if not __import__('os').environ.get('SLURM_JOB_ID'):raise RuntimeError('Private CPU restoration requires allocation')
 return native_command(site,{'operation':'restore_cpu_quote','baseline':baseline})


from lab_generate_skill.shopping_review_creation import evaluate_review as base_review
from email import policy
from email.parser import BytesParser
from html import unescape

def review_judge(c,page,initial,current,origin):
 s=c['offline_training'];mapped=c|{'review_creation':{'product_id':s['product_id'],'stars':s['stars'],'title':s['title']}};j=base_review(mapped,page,initial,current,site_origin=origin)
 if j['status']=='unknown':return j
 rows=current['reviews']['added'];j['checks'].update(exact_review_detail_saved=len(rows)==1 and rows[0]['detail']==s['detail'],requested_reviewer_nickname=len(rows)==1 and rows[0]['nickname']==s['nickname']);ok=all(j['checks'].values());return j|{'version':VERSION,'status':'success'if ok else'failure','reward':float(ok)}


def normalized(s):return' '.join(unescape(s).split())
def mail_judge(c,page,before,now,site):
 from bs4 import BeautifulSoup
 known={r['file']for r in before['messages']};added=[r for r in now['messages']if r['file']not in known];s=c['offline_training']['form'];checks={'page_valid':valid_initial_page(page,site_origin=site.url),'native_local_sink_only':now.get('external_delivery')is False and now.get('backend')=='local_sendmail_capture_v1','one_native_message_saved':len(added)==1,'old_mail_unchanged':all(r in now['messages']for r in before['messages'])}
 if len(added)==1:
  message=BytesParser(policy=policy.default).parsebytes((Path(site.mail_outbox)/added[0]['file']).read_bytes());texts=[]
  for part in message.walk():
   if part.get_content_type()in('text/plain','text/html'):
    body=part.get_content();texts.extend(normalized(x)for x in(BeautifulSoup(body,'html.parser').stripped_strings if part.get_content_type()=='text/html'else body.splitlines()))
  checks.update(exact_comment_saved=normalized(s['comment'])in texts,exact_contact_email_saved=any(normalized(x)in (normalized(s['email']),normalized('Email: '+s['email']))for x in texts),exact_contact_name_saved=any(normalized(x)in(normalized(s['name']),normalized('Name: '+s['name']))for x in texts),exact_contact_phone_saved=any(normalized(x)in(normalized(s['telephone']),normalized('Phone Number: '+s['telephone']))for x in texts))
 passed=all(checks.values());return {'version':VERSION,'status':'success'if passed else'failure','reward':float(passed),'checks':checks,'reason':None}

