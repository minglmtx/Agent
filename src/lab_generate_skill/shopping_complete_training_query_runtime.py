"""Normal shared-runner lifecycle for explicit complete native training queries.

This module supplies no actor action, intermediate reward or hidden oracle value.
The existing terminal-only NativeReadHooks slot owns reset/reference verification.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
try:
 from . import shopping_complete_training_query as rule
except ImportError:
 import shopping_complete_training_query as rule
from lab_generate_skill.io_utils import atomic_write_json
from lab_generate_skill.site_query_rules import query_goal
VERSION=rule.VERSION

def enabled(c):
 if c.get('query',{}).get('family')!=rule.FAMILY:return False
 rule.validate(c)
 if any(c.get(k)for k in ('offline_training','gitlab_native_read','reddit_native_read','gitlab_navigation_goal','preference_goal_state','native_csv_export','submission','review_creation','newsletter','checkout','cart')):raise ValueError('One optional complete query lifecycle required')
 return True

def require_admission(c,proof):enabled(c);return rule.require_admission(c,proof)
def require_original_binding(c,original,inventory):enabled(c);return rule.require_original_binding(c,original,inventory)
def fields(c):enabled(c);return list(c['query']['fields'])
def public_goal(c):enabled(c);return query_goal(c)

def profile_for_contracts(contracts):
 rows=list(contracts)
 if not any(enabled(c)for c in rows):return {}
 if any(c.get('domain')!='shopping'or c.get('initial_state_revision',{}).get('local_mail_capture')is not True for c in rows):raise ValueError('Explicit same-site private local-mail snapshot required')
 return {'shopping_capture_mail':True}

def normal_reference(site,c):
 """Reuse only the freshly verified, same-task startup reference once.

 This is a private lifecycle handoff, never a global/stale oracle cache. Any
 subsequent reference call performs a complete fresh native read.
 """
 enabled(c);saved=getattr(site,'_complete_native_query_initial_handoff',None)
 if saved is not None:
  if saved['contract_fingerprint']!=rule.fingerprint(c):raise ValueError('Initial private reference belongs to another task')
  delattr(site,'_complete_native_query_initial_handoff');return deepcopy(saved['reference'])
 return rule.reference(site,c)

class CompleteNativeQueryHooks:
 def __init__(self,c,proof,directory):
  self.initial=require_admission(c,proof);self.contract=deepcopy(c);self.proof=deepcopy(proof);self.directory=Path(directory);self.prepared=self.scored=False;self.context=self.initial_page=None;self.trace=None
 def prepare(self,site,username):
  if self.prepared:raise ValueError('One isolated task initialization required')
  startup=rule.initialize_startup(site,username,self.contract);actual=rule.reference(site,self.contract,email=username);fingerprint=site.fingerprint();expected=self.proof['cycles'][0]
  if actual!=self.initial or fingerprint!=expected['initial_fingerprint']or actual['source_state']['complete_native_protection']!=expected['full_protected_before']:raise ValueError('Fresh complete native oracle/reset differs from both admitted cold controls')
  if startup['local_mail_profile']!={'backend':'local_sendmail_capture_v1','external_delivery':False}:raise ValueError('Declared isolated local mail profile missing')
  if getattr(site,'_complete_native_query_initial_handoff',None)is not None:raise ValueError('Initial private handoff already occupied')
  self.site,self.username=site,username;self.before=actual;self.fingerprint=fingerprint;self.prepared=True
  site._complete_native_query_initial_handoff={'contract_fingerprint':rule.fingerprint(self.contract),'reference':deepcopy(actual)}
  atomic_write_json(self.directory/'complete-native-query-baseline.json',{'startup':startup,'reference':actual,'initial_fingerprint':fingerprint,'oracle_sent_to_actor':False})
 def attach(self,context):
  if not self.prepared or self.context is not None:raise ValueError('One prepared browser context required')
  self.context=context
 def observe_initial(self,page):
  if self.initial_page is not None or page.context is not self.context:raise ValueError('One bound initial page required')
  actual=urlsplit(page.url);expected=urlsplit(self.contract['start_path']);origin=urlsplit(self.site.url)
  if(actual.scheme,actual.netloc)!=(origin.scheme,origin.netloc)or(actual.path,actual.query,actual.fragment)!=(expected.path,expected.query,expected.fragment):raise ValueError('Declared task start changed')
  self.initial_page=page
 def capture_terminal(self,page,terminal):
  if self.initial_page is None or page.context is not self.context:raise ValueError('Bound terminal page required')
 def provide_trace(self,trace):
  if self.trace is not None:raise ValueError('One finished trace required')
  self.trace=deepcopy(trace)
 def score_terminal(self,site,page,*,runtime_error=None):
  if not self.prepared or self.scored or site is not self.site:raise ValueError('One independent terminal judgment required')
  self.scored=True;after=None
  try:
   after=rule.reference(site,self.contract,email=self.username);integrity=after==self.before and site.fingerprint()==self.fingerprint
   from lab_generate_skill.admin_pilot import final_answer
   if self.trace is None:raise ValueError('Finished actor trace required before judgment')
   answer=final_answer(self.trace)
   judgment=rule.evaluate(self.contract,page,answer,self.before,after,site_origin=site.url,runtime_error=runtime_error)
   judgment['checks']['complete_native_reference_unchanged']=integrity
   if judgment['status']!='unknown'and not integrity:judgment.update(status='failure',reward=0.0)
  except Exception as exc:
   integrity=False;judgment={'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Complete native terminal capture unavailable','exception_type':type(exc).__name__}
  atomic_write_json(self.directory/'complete-native-query-terminal.json',{'before':self.before,'after':after,'judgment':judgment,'terminal_only':True,'oracle_sent_to_actor':False});return judgment,integrity
 def close(self):
  if self.prepared and getattr(self.site,'_complete_native_query_initial_handoff',None)is not None:delattr(self.site,'_complete_native_query_initial_handoff')

def feedback(j):
 return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),'checks':[{'name':k,'passed':v,'condition':k.replace('_',' ')+'.'}for k,v in j.get('checks',{}).items()],'action_sequence_provided':False,'private_reference_values_provided':False}
