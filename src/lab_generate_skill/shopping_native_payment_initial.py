"""Declared native payment-stage initialization, completed before any actor.

Only actual local Magento controls are used. No runtime action, success hint,
HTML modification, foreign-row update, or repeated session correction exists.
"""
import copy,json,re
from pathlib import Path
from urllib.parse import urlsplit
from .browser_driver import initialization_playwright
from lab_generate_skill.site_auth import credentials,login
from lab_generate_skill.browser_request_policy import install_local_network_policy
from lab_generate_skill.runtime_watchdog import deadline_scope

STAGE={'version':1,'name':'payment','native_shipping_next_before_actor':True,'native_initial_payment':'checkmo','owned_clock_normalization_before_actor_only':True,'preserve_foreign_rows_all_columns':True}
FIELDS=('selectedShippingAddress','selectedShippingRate','selectedBillingAddress','selectedPaymentMethod')

def stage(c):
 value=c.get('initial_state_revision',{}).get('native_checkout_stage')
 if value is None:return None
 if c.get('offline_training',{}).get('mode')not in('payment','billing')or c.get('start_path')!='/checkout/#payment' or not c.get('is_explicit_derivative')or c.get('original_evaluation_equivalence')is not False or not c.get('initial_state_revision',{}).get('reason'):raise ValueError('Declared local native payment-stage derivative required')
 if set(value)!=set(STAGE)or any(type(value[k])is not type(v)or value[k]!=v for k,v in STAGE.items()):raise ValueError('Exact pre-actor native checkout stage required')
 if c['offline_training']['mode']=='payment'and c['offline_training'].get('initial_method')!='checkmo':raise ValueError('Native initial payment method disagrees')
 return copy.deepcopy(STAGE)

def wait_shipping(page):
 page.wait_for_function("""() => {const v=e=>!!e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';return [...document.querySelectorAll('.shipping-address-item.selected-item')].some(v)&&[...document.querySelectorAll('#co-shipping-method-form input[type=radio]')].some(e=>v(e)&&e.checked)&&![...document.querySelectorAll('.loading-mask')].some(v)}""",timeout=30000)

def wait_payment(page, *, expected_selected=None, timeout_ms=30000):
 # Radio nodes can become visible before Magento restores checkout-data.
 # Before actor start, wait for the declared native selection as well as DOM
 # availability. This only observes: it never selects, clicks or writes storage.
 if expected_selected not in (None, 'checkmo'):
  raise ValueError('Only the declared initial native payment may be awaited')
 if not isinstance(timeout_ms,int) or isinstance(timeout_ms,bool) or not 1 <= timeout_ms <= 30000:
  raise ValueError('A finite initial readiness deadline is required')
 page.wait_for_function("""expected => {
 const v=e=>!!e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const radios=[...document.querySelectorAll('#payment .payment-method-title input[type=radio]')];
 const selected=radios.filter(e=>e.checked).map(e=>e.value);
 return radios.filter(e=>v(e)&&!e.disabled).length===2
   && ![...document.querySelectorAll('.loading-mask')].some(v)
   && (expected===null||(selected.length===1&&selected[0]===expected));
 }""",arg=expected_selected,timeout=timeout_ms)

def native_storage(page):
 value=page.evaluate("""() => {const d=JSON.parse(localStorage.getItem('mage-cache-storage')||'{}')['checkout-data']||{};return Object.fromEntries(['selectedShippingAddress','selectedShippingRate','selectedBillingAddress','selectedPaymentMethod'].filter(k=>Object.hasOwn(d,k)).map(k=>[k,d[k]]))}""")
 if not isinstance(value,dict)or not {'selectedShippingAddress','selectedShippingRate','selectedPaymentMethod'}<=set(value)or set(value)-set(FIELDS)or value['selectedPaymentMethod']!='checkmo'or any(v is not None and(not isinstance(v,str)or not v)for v in value.values()):raise ValueError('Actual native initialized checkout selections unavailable')
 return value

def install_initial_storage(context,origin,value):
 if not isinstance(value,dict)or set(value)-set(FIELDS)or value.get('selectedPaymentMethod')!='checkmo':raise ValueError('Only captured native checkout selections allowed')
 p=urlsplit(origin)
 if p.scheme not in('http','https')or not p.netloc:raise ValueError('Exact isolated local origin required')
 target=p.scheme+'://'+p.netloc
 # Once per context: the first actual initial checkout document only. Actor
 # reloads, subsequent tabs and other origins cannot restore the initial choice.
 context.add_init_script("""(()=>{const o=%s,d=%s,k='lab-native-payment-initial-v1';if(location.origin!==o||location.pathname!='/checkout/'||location.hash!=='#payment'||localStorage.getItem(k))return;const m=JSON.parse(localStorage.getItem('mage-cache-storage')||'{}');m['checkout-data']={...(m['checkout-data']||{}),...d};localStorage.setItem('mage-cache-storage',JSON.stringify(m));localStorage.setItem(k,'initialized-once')})()"""%(json.dumps(target),json.dumps(value)))

def initialize(site,username,c,before,rule):
 declared=stage(c)
 if declared is None:return None
 auth=credentials(site.root,'shopping')
 if auth['username']!=username:raise ValueError('Declared initialized customer differs')
 ui=storage=None
 with initialization_playwright()as pw:
  browser=pw.chromium.launch(headless=True);context=None
  try:
   context=browser.new_context(viewport={'width':1280,'height':720});install_local_network_policy(context,urlsplit(site.url).netloc);page=context.new_page();page.set_default_timeout(15000)
   login(page,site,auth);page.goto(site.url+'/checkout/#shipping',wait_until='domcontentloaded',timeout=45000);wait_shipping(page)
   page.get_by_role('button',name='Next',exact=True).click(timeout=15000);wait_payment(page)
   page.locator('#payment .payment-method-title input[value="checkmo"]').check(timeout=10000)
   from lab_generate_skill.shopping_checkout import read_checkout_page
   ui=read_checkout_page(page)
   ui['payment_methods']=page.locator('#payment .payment-method-title input[type=radio]').evaluate_all('es=>es.map(e=>({value:e.value,checked:e.checked,disabled:e.disabled}))')
   if str(ui.get('quote_id'))!=str(before['quote_id'])or str(ui.get('customer_id'))!=str(before['customer_id'])or [r['value']for r in ui['payment_methods']if r['checked']]!=['checkmo']:raise ValueError('Native initialized payment quote/customer/choice differs')
   actual=urlsplit(page.url);expected=urlsplit(site.url)
   if (actual.scheme,actual.netloc)!=(expected.scheme,expected.netloc)or actual.path!='/checkout/'or actual.fragment!='payment':raise ValueError('Native Shipping Next did not reach declared payment stage')
   storage=native_storage(page)
  finally:
   try:
    if context is not None:
     with deadline_scope('native_payment_initial_context_close',30):context.close()
   finally:
    with deadline_scope('native_payment_initial_browser_close',30):browser.close()
 normalized=rule.native_command(site,{'operation':'normalize_pre_actor_payment_clocks','email':username,'captured_before':before,'stage':declared,'pre_actor_initialization_only':True})
 if normalized.get('pre_actor_only')is not True or normalized.get('foreign31_unchanged')is not True:raise ValueError('Private native initialization receipt unavailable')
 return {'version':'native-payment-stage-initial-v1','stage':declared,'native_ui':ui,'native_checkout_storage':storage,'normalization':normalized,'actor_actions':0,'api_calls':0,'runtime_actions_forbidden':True}


def full_snapshot(site, *, raw_rows_directory=None):
 """Return the unchanged full31 fingerprint; optionally save private quote rows.

 The PHP cursor emits the exact JSONL bytes it hashes, without another SELECT.
 Caller-owned evidence is separate from the returned fingerprint and must never
 be projected into an Actor request. Existing callers perform no file capture.
 """
 import hashlib,shutil,tempfile
 php=Path(__file__).with_name('shopping_complete_query_protection.php')
 command=['php','-r',php.read_text().removeprefix('<?php')]
 destination=None;staging=None
 if raw_rows_directory is not None:
  destination=Path(raw_rows_directory)
  if not destination.is_absolute():raise ValueError('Absolute private evidence destination required')
  destination.mkdir(mode=0o700,exist_ok=False)
  staging=Path(tempfile.mkdtemp(prefix='protected-rows-',dir=site.state))
  command+=['--','/state/'+staging.name]
 try:
  value=json.loads(site.command(command,capture_output=True,text=True,timeout=240).stdout)
  _validate_full_snapshot(value)
  if destination is not None:
   rows={}
   for table in ('quote','quote_address'):
    source=staging/(table+'.jsonl');data=source.read_bytes();expected=value['tables'][table]
    if hashlib.sha256(data).hexdigest()!=expected['sha256'] or len(data.splitlines())!=expected['rows']:
     raise ValueError('Private row bytes differ from same-cursor fingerprint')
    target=destination/source.name
    with target.open('xb')as handle:handle.write(data)
    target.chmod(0o600)
    rows[table]=dict(file=target.name,sha256=expected['sha256'],rows=expected['rows'],bytes=len(data))
   from .io_utils import atomic_write_json
   atomic_write_json(destination/'manifest.json',dict(version='shopping-private-quote-rows-v1',
       encoding='PHP JSON_THROW_ON_ERROR JSONL, exact hashed cursor bytes',tables=rows,
       additional_sql_queries=0,actor_input=False))
  return value
 finally:
  if staging is not None:shutil.rmtree(staging)


def _validate_full_snapshot(value):
 from lab_generate_skill.shopping_search_protection import TABLES
 expected=set(TABLES)|{'quote','quote_address','quote_payment','sales_order_status_history','review','review_detail','review_store','review_entity_summary','rating_option_vote'}
 if value.get('version')!='shopping-complete-native-query-full-rows-v1'or set(value.get('tables',{}))!=expected or value.get('statement_budget_seconds')!=20:raise ValueError('Exact 31 native tables required')
 for row in value['tables'].values():
  if row.get('ignored_columns')!=[]or type(row.get('rows'))is not int or row['rows']<0 or not row.get('primary_key')or not set(row['primary_key'])<=set(row.get('columns',[]))or not re.fullmatch('[0-9a-f]{64}',row.get('sha256','')):raise ValueError('Complete native rows/columns/digest missing')


def validate_evidence(c,row):
 declared=stage(c);receipt=row.get('native_payment_stage',{});state=row.get('initial_state',{})
 if receipt.get('version')!='native-payment-stage-initial-v1'or receipt.get('stage')!=declared or type(receipt.get('actor_actions'))is not int or receipt['actor_actions']!=0 or type(receipt.get('api_calls'))is not int or receipt['api_calls']!=0 or receipt.get('runtime_actions_forbidden')is not True:raise ValueError('Actual pre-actor native initialization evidence required')
 normalize=receipt.get('normalization',{})
 if normalize.get('pre_actor_only')is not True or normalize.get('foreign31_unchanged')is not True or normalize.get('state')!=state:raise ValueError('Exact initialized native state evidence missing')
 cache=receipt.get('native_checkout_storage',{});ui=receipt.get('native_ui',{})
 if not {'selectedShippingAddress','selectedShippingRate','selectedPaymentMethod'}<=set(cache)or set(cache)-set(FIELDS)or cache.get('selectedPaymentMethod')!='checkmo'or [r['value']for r in ui.get('payment_methods',[])if r.get('checked')]!=['checkmo']or str(ui.get('quote_id'))!=str(state.get('quote_id'))or str(ui.get('customer_id'))!=str(state.get('customer_id')):raise ValueError('Native initial selections/quote/customer mismatch')
 from lab_generate_skill.shopping_search_protection import TABLES
 expected=set(TABLES)|{'quote','quote_address','quote_payment','sales_order_status_history','review','review_detail','review_store','review_entity_summary','rating_option_vote'}
 protected=row.get('full_protected_before',{})
 if set(protected.get('tables',{}))!=expected or set(state.get('foreign_protected',{}))!=expected:raise ValueError('Full31 rows/foreign coverage unavailable')
 for item in protected['tables'].values():
  if item.get('ignored_columns')!=[]or not item.get('primary_key')or not set(item['primary_key'])<=set(item.get('columns',[]))or not re.fullmatch('[0-9a-f]{64}',item.get('sha256','')):raise ValueError('Complete protected clock/column evidence required')
 for item in state['foreign_protected'].values():
  if not item.get('primary_key')or not set(item['primary_key'])<=set(item.get('columns',[]))or not re.fullmatch('[0-9a-f]{64}',item.get('sha256','')):raise ValueError('Complete foreign clock/column evidence required')
