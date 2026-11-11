"""Optional normal lifecycle for declared native/offline Shopping training tasks.

Uses the shared runner's existing native-goal hook slot. No actor actions,
recovery hints, hidden references or intermediate success checks are produced.
"""
from copy import deepcopy
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from pathlib import Path
from urllib.parse import urlsplit
try:
 from . import shopping_offline_training as rule
 from . import shopping_native_payment_initial as payment_initial
except ImportError:
 import shopping_offline_training as rule
 import shopping_native_payment_initial as payment_initial
from lab_generate_skill.shopping_review_creation import review_state
from lab_generate_skill.shopping_search_protection import protected_snapshot
from lab_generate_skill.local_mail_capture import evidence as mail_evidence
from lab_generate_skill.private_mail_evidence import capture_new_messages
from lab_generate_skill.shopping_checkout import read_checkout_page
from lab_generate_skill.io_utils import atomic_write_json

from lab_generate_skill import shopping_quote_integrity as quote_guard
from lab_generate_skill import shopping_review_integrity as original31

VERSION=rule.VERSION
AUTHORIZED_TARGET_WRITES=False

def enabled(c):
 if 'offline_training'not in c:return False
 rule.validate(c);payment_initial.stage(c)
 if any(c.get(k)for k in('gitlab_native_read','reddit_native_read','gitlab_navigation_goal','preference_goal_state','native_csv_export','query','submission','review_creation','newsletter','checkout','cart')):
  raise ValueError('Exactly one optional native training lifecycle required')
 return True

def require_admission(c,proof):
 enabled(c);rule.require_admission(c,proof);original31.require_proof(c,proof)
 return deepcopy(proof['cycles'][0]['initial_state'])

def require_original_binding(c,original,inventory):
 enabled(c)
 if not isinstance(original,dict)or rule.fingerprint(original)!=rule.fingerprint(c):raise ValueError('Exact prepared wave contract required')
 if not isinstance(inventory,dict)or inventory.get('task_id')!=c['source_task_id']or inventory.get('domain')!='shopping'or inventory.get('heldout_quarantine'):raise ValueError('Actual development source required')
 if inventory.get('goal')!=c['original_goal']or any(inventory.get(k)!=c.get(k)for k in('source_trace_ids','recorded_start_urls')):raise ValueError('Original source provenance changed')
 def path(url):
  p=urlsplit(url);return(p.path or'/')+('?' +p.query if p.query else'')+('#'+p.fragment if p.fragment else'')
 paths=list(map(path,inventory['recorded_start_urls']))
 if c.get('recorded_start_paths')!=paths:raise ValueError('Recorded starts changed')
 rev=c.get('goal_revision',{})
 if rev.get('original_goal')!=inventory['goal']or rev.get('derived_goal')!=c['goal']or rev.get('version')!=1 or not rev.get('reason'):raise ValueError('Explicit exact goal revision required')
 if c['start_path']!=paths[0]:
  rev=c.get('start_revision',{})
  if rev.get('original_start')!=paths[0]or rev.get('derived_start')!=c['start_path']or rev.get('version')!=1 or not rev.get('reason'):raise ValueError('Explicit start revision required')
 elif c.get('start_revision'):raise ValueError('Spurious start revision')
 rev=c.get('initial_state_revision',{})
 if rev.get('fixture_version')!=c['offline_training']['fixture_version']or rev.get('external_delivery')is not False or not rev.get('reason')or c.get('no_external_response_required')is not True:raise ValueError('Explicit local native fixture required')


def profile_for_contracts(contracts):
 enabled_rows=[c for c in contracts if enabled(c)];mail=[c for c in enabled_rows if c['offline_training']['mode']in('review','contact')]
 if mail and len(mail)!=len(contracts):raise ValueError('Local mail capture training tasks require a dedicated same-site manifest')
 return {'shopping_capture_mail':bool(mail)}if enabled_rows else{}


def initialize(site,username,c):
 """Shared CPU/normal startup. Native fixture completes before observation."""
 enabled(c);mode=c['offline_training']['mode'];fixture=None
 if payment_initial.stage(c)is not None and getattr(site,'native_payment_stage',None):raise ValueError('One declared pre-actor stage initialization required')
 if mode not in('review','contact'):fixture=rule.prepare_fixture(site,username,c)
 declared=payment_initial.stage(c);stage_receipt=None
 if declared is not None:
  if getattr(site,'native_payment_stage',None):raise ValueError('One declared pre-actor stage initialization required')
  site.native_payment_stage=declared
  captured=rule.state(site,username);original_full31=payment_initial.full_snapshot(site)
  try:stage_receipt=payment_initial.initialize(site,username,c,captured,rule)
  except BaseException:
   rule.restore_selected_quote(site,captured)
   if rule.state(site,username)!=captured or payment_initial.full_snapshot(site)!=original_full31:raise ValueError('Failed pre-actor native initialization was not fully restored')
   raise
  site.native_payment_stage_receipt=stage_receipt
 independent=quote_guard.capture(site,username,strict_legacy31=declared is not None)if mode not in('review','contact')else None
 quote=independent['owned_quote_state']if independent is not None else rule.state(site,username)
 if declared is not None and mode=='billing'and all(str(rule.row_by_type(quote['addresses'],'billing').get(k)or'')==str(v)for k,v in c['offline_training']['address'].items()):raise ValueError('Declared billing target already satisfied before actor')
 protected=(independent['complete_physical31']if declared is not None else independent['compatibility_legacy22'])if independent is not None else protected_snapshot(site)
 if mode=='review':initial={'review':review_state(site,username),'quote':quote,'mail':mail_evidence(site.mail_outbox)}
 elif mode=='contact':initial={'quote':quote,'mail':mail_evidence(site.mail_outbox)}
 else:initial=quote
 if mode in('review','contact')and(initial['mail'].get('backend')!='local_sendmail_capture_v1'or initial['mail'].get('external_delivery')is not False):raise ValueError('Declared private local native mail profile missing')
 return {'native_static_assets':deepcopy(site.native_static_assets),'fixture':fixture,'initial_state':initial,'full_protected_before':protected,'initial_fingerprint':site.fingerprint(),**({'independent_foreign31':independent}if independent is not None else{}),**({'native_payment_stage':stage_receipt}if stage_receipt is not None else{})}


def current_payment_controls(page):
 ui=read_checkout_page(page)
 ui['payment_methods']=page.locator('#payment .payment-method-title input[type=radio]').evaluate_all("es=>es.map(e=>({value:e.value,checked:e.checked,visible:!!e.getClientRects().length,disabled:e.disabled}))")
 return ui


class ShoppingOfflineHooks:
 def __init__(self,c,proof,directory):
  self.initial=require_admission(c,proof);self.contract=deepcopy(c);self.proof=deepcopy(proof);self.directory=Path(directory);self.prepared=self.scored=False;self.context=self.initial_page=None;self.ui=None
 def prepare(self,site,username):
  if self.prepared:raise ValueError('One isolated native task initialization required')
  value=initialize(site,username,self.contract);expected=self.proof['cycles'][0]
  keys=('initial_state','full_protected_before','initial_fingerprint')+(('native_static_assets',)if self.contract.get('initial_state_revision',{}).get('native_static_publication')else())
  if any(value[k]!=expected[k]for k in keys):
   # Full private comparison is archived before refusal, so initialization
   # failures remain diagnosable without another database traversal or model.
   atomic_write_json(self.directory/'offline-training-initialization-mismatch.json',{
    'version':'shopping-native-initialization-comparison-v1',
    'task_id':self.contract['task_id'],'source_task_id':self.contract['source_task_id'],
    'compared_fields':list(keys),'field_matches':{k:value[k]==expected[k]for k in keys},
    'actual':{k:deepcopy(value[k])for k in keys},
    'expected_two_cold_baseline':{k:deepcopy(expected[k])for k in keys},
    'private_diagnostic_only':True,'actor_started':False,'baseline_accepted':False,
    'additional_database_reads':0,'api_calls':0})
   raise ValueError('Actual declared native fixture differs from both cold controls')
  if payment_initial.stage(self.contract)is not None:
   if value['native_payment_stage']['native_checkout_storage']!=expected['native_payment_stage']['native_checkout_storage']:raise ValueError('Actual initialized native selections differ from both cold controls')
  if self.contract['offline_training']['mode']in('review','contact'):
   baseline=original31.capture(site,username,self.contract)
   if baseline['full31_before']!=expected['complete_original_before']:raise ValueError('Actual original31 differs from both cold controls')
   value['all_original31']=baseline
  self.site,self.username=site,username;self.before=value;self.prepared=True;atomic_write_json(self.directory/'offline-training-baseline.json',value)
 def attach(self,context):
  if not self.prepared or self.context is not None:raise ValueError('One prepared context required')
  self.context=context
  if payment_initial.stage(self.contract)is not None:payment_initial.install_initial_storage(context,self.site.url,self.before['native_payment_stage']['native_checkout_storage'])
 def observe_initial(self,page):
  if self.initial_page is not None or page.context is not self.context:raise ValueError('One bound initial observation required')
  actual=urlsplit(page.url);expected=urlsplit(self.contract['start_path']);origin=urlsplit(self.site.url)
  if (actual.scheme,actual.netloc)!=(origin.scheme,origin.netloc)or actual.path!=expected.path or actual.query!=expected.query or actual.fragment!=expected.fragment:raise ValueError('Declared task start changed')
  if payment_initial.stage(self.contract)is not None:
   readiness_error=None
   try:payment_initial.wait_payment(page,expected_selected='checkmo')
   except PlaywrightTimeoutError as error:readiness_error=type(error).__name__
   ui=current_payment_controls(page)
   matches={'quote_identity':str(ui.get('quote_id'))==str(self.initial['quote_id']),
    'customer_identity':None,'selected_payment_methods':None}
   if matches['quote_identity']:
    matches['customer_identity']=str(ui.get('customer_id'))==str(self.initial['customer_id'])
    if matches['customer_identity']:
     matches['selected_payment_methods']=[r['value']for r in ui['payment_methods']if r['checked']]==['checkmo']
   quote_read_performed=all(matches.values())
   actual_quote=rule.state(self.site,self.username)if quote_read_performed else None
   matches['complete_owned_quote_state']=actual_quote==self.initial if quote_read_performed else None
   if readiness_error is not None or not all(matches.values()):
    atomic_write_json(self.directory/'native-payment-initial-observation-mismatch.json',{
     'version':'native-payment-private-initial-comparison-v1','task_id':self.contract['task_id'],
     'source_task_id':self.contract['source_task_id'],'field_matches':matches,'readiness_error_type':readiness_error,
     'actual_ui':deepcopy(ui),'actual_complete_owned_quote':deepcopy(actual_quote),
     'owned_quote_read_performed':quote_read_performed,
     'expected_complete_owned_quote':deepcopy(self.initial),'expected_selected_payment_methods':['checkmo'],
     'page_url':page.url,'private_diagnostic_only':True,'actor_started':False,
     'baseline_accepted':False,'additional_database_reads':0,'api_calls':0})
    raise ValueError('Native payment initial observation differs before actor')
  self.initial_page=page
 def capture_terminal(self,page,terminal):
  if self.initial_page is None or page.context is not self.context:raise ValueError('Bound terminal page required')
  if self.contract['offline_training']['mode']=='payment':self.ui=current_payment_controls(page);terminal['offline_training_payment_terminal']=deepcopy(self.ui)
 def score_terminal(self,site,page,*,runtime_error=None):
  if not self.prepared or self.scored or site is not self.site:raise ValueError('One independent judgment after termination required')
  self.scored=True;mode=self.contract['offline_training']['mode'];quote=protected=current=complete=native_mail_capture=None
  try:
   independent=quote_guard.capture(site,self.username,strict_legacy31=payment_initial.stage(self.contract)is not None)if mode not in('review','contact')else None
   quote=independent['owned_quote_state']if independent is not None else rule.state(site,self.username)
   protected=(independent['complete_physical31']if payment_initial.stage(self.contract)is not None else independent['compatibility_legacy22'])if independent is not None else protected_snapshot(site)
   if mode=='review':
    current={'review':review_state(site,self.username,self.initial['review']),'quote':quote,'mail':mail_evidence(site.mail_outbox)}
    judgment=rule.review_judge(self.contract,page,self.initial['review'],current['review'],site.url)
    integrity=quote==self.initial['quote']and protected==self.before['full_protected_before']and all(self.initial['review'][k]['protected']==current['review'][k]['protected']for k in('reviews','votes'))and all(r in current['mail']['messages']for r in self.initial['mail']['messages'])and current['mail'].get('external_delivery')is False
   elif mode=='contact':
    current={'quote':quote,'mail':mail_evidence(site.mail_outbox)};judgment=rule.mail_judge(self.contract,page,self.initial['mail'],current['mail'],site);integrity=quote==self.initial['quote']and protected==self.before['full_protected_before']
    native_mail_capture=capture_new_messages(self.initial['mail'],current['mail'],site.mail_outbox)
   else:
    current=quote;judgment=rule.evaluate(self.contract,page,self.initial,quote,site_origin=site.url,ui=self.ui,runtime_error=runtime_error)
    # All original foreign records and configuration stay exact; the owned
    # quote is fully read and validated with task-specific permitted changes.
    integrity=quote['foreign_protected']==self.initial['foreign_protected']and quote['configuration']==self.initial['configuration']and rule.unchanged_cart(self.initial,quote,mode,self.contract['offline_training'])
   if independent is not None:
    strict_integrity=quote_guard.unchanged(self.before['independent_foreign31'],independent)
    judgment['checks']['complete31_foreign_records_all_fields_unchanged']=strict_integrity
    integrity=integrity and strict_integrity
    atomic_write_json(self.directory/'offline-training-independent-foreign31-terminal.json',independent)
   if mode in('review','contact'):
    complete=original31.terminal(site,self.before['all_original31'],current.get('review'))
    integrity=integrity and complete['integrity']
   if runtime_error:judgment={'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Runtime prevented reliable terminal judgment'}
   judgment['checks']['complete_native_non_target_records_unchanged']=integrity
   if judgment['status']!='unknown'and not integrity:judgment.update(status='failure',reward=0.0)
  except Exception as exc:
   integrity=False;judgment={'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Native terminal capture unavailable','exception_type':type(exc).__name__}
  atomic_write_json(self.directory/'offline-training-terminal-state.json',{'current':current,'native_mail_capture':native_mail_capture,'legacy_proof_protection_before':self.before['full_protected_before'],'legacy_proof_protection_after':protected,'legacy_proof_protection_table_count':len(self.before['full_protected_before']['tables']),'owned_quote_before':self.initial.get('quote',self.initial),'owned_quote_after':quote,'all_original31_before':self.before.get('all_original31'),'all_original31_terminal':complete,'judgment':judgment,'integrity':integrity,'terminal_only':True})
  return judgment,integrity
 def close(self):pass


def feedback(j):
 return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),'checks':[{'name':k,'passed':v,'condition':k.replace('_',' ')+'.'}for k,v in j.get('checks',{}).items()],'action_sequence_provided':False,'private_reference_values_provided':False}
