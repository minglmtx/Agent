"""Declared native search completion: results or a previously observed result post.

Uses the ordinary terminal-only read-hook slot and complete13 guard. This is a
public lexical-search training boundary, not a semantic recall judge. It does
not select an actor action or accept arbitrary posts after any old search.
"""
from copy import deepcopy
import hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit,unquote
from . import reddit_final_read_runtime as shared
from . import reddit_remaining_normal as public
from . import reddit_search as search
from .reddit_native_read_runtime import validate_complete_snapshot
from .source_revision_binding import binding,fingerprint,require_source_binding
from .site_navigation_rules import valid_initial_page
from .site_database import select_rows
from .io_utils import atomic_write_json
VERSION='reddit-native-search-results-or-observed-post-v1'
PROOF='reddit-native-search-results-or-observed-post-two-cold-v1'
EXPECTED={'initial_no_op':'success','positive':'success','positive_post':'success',
          'wrong_target':'failure','unobserved_search_post':'failure','404':'failure','login':'failure'}

def enabled(c):
 if 'reddit_search_completion'not in c:return False
 if c.get('domain')!='reddit'or c.get('heldout_quarantine')is not False or c.get('eligible_for_training')is not False:raise ValueError('Explicit development-only native search family required')
 spec=c['reddit_search_completion']
 if set(spec)!={'version','query','boundary'}or spec['version']!=VERSION or spec['boundary']!='results_or_observed_matching_post'or not isinstance(spec['query'],str)or not spec['query'].strip():raise ValueError('Declared public native search boundary required')
 if any(c.get(k)for k in('reddit_native_task','reddit_original_reading','reddit_maximum_query','query','forum_creation','submission','membership','wiki','search')):raise ValueError('Only one read-only native search family required')
 binding(c);return True

def fields(c):enabled(c);return []
def public_goal(c):enabled(c);return c['goal']
def require_original_binding(c,original,inventory):return require_source_binding(c,original,inventory,domain='reddit')
def provenance():
 return dict(shared.provenance(),search_completion_runtime_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
   native_search_sha256=hashlib.sha256(Path(search.__file__).read_bytes()).hexdigest(),
   native_page_reader_sha256=hashlib.sha256(Path(public.__file__).read_bytes()).hexdigest())
def reference(site,c,username):
 enabled(c);query=c['reddit_search_completion']['query'];rows=search.search_reference(site,query)
 ids=[r['id']for r in rows if r['kind']=='submission']
 if any(type(i)is not int or i<=0 for i in ids):raise ValueError('Exact native matching post identities required')
 posts=[]if not ids else select_rows(site,"SELECT s.id,s.title,s.visibility,f.name AS forum FROM submissions s JOIN forums f ON f.id=s.forum_id WHERE s.id IN ("+','.join(map(str,ids))+') ORDER BY s.id')
 if len(posts)!=len(ids):raise ValueError('Every native matching post must be independently identified')
 accounts=select_rows(site,"SELECT id,username FROM users WHERE username='"+username.replace("'","''")+"'")
 if len(accounts)!=1:raise ValueError('One native account required')
 return {'query':query,'search_rows':rows,'matching_posts':posts,'account':accounts[0]}

def evaluate(c,private,observations,terminal,*,site_origin):
 enabled(c)
 result={'terminal_native_document_valid':valid_initial_page(terminal,site_origin=site_origin),
   'validated_native_search_observed':False,'matching_native_result_or_observed_post':False}
 if not result['terminal_native_document_valid']:return _judgment(result)
 validated=[]
 for row in observations:
  if not isinstance(row,dict)or not valid_initial_page(row.get('page'),site_origin=site_origin):continue
  if row.get('native',{}).get('url')!=row['page']['url']:raise ValueError('Actual native issued document binding differs')
  if urlsplit(row['page']['url']).path!='/search'or not isinstance(row.get('actual_issued_ax'),str):continue
  if 'search'not in row:continue
  checks=search.search_checks({'query':private['query'],'reference':private['search_rows'],'require_submission':True},row['search'],row['page']['url'])
  if checks and all(checks.values()):validated.append(row)
 result['validated_native_search_observed']=bool(validated)
 if not validated:return _judgment(result)
 path=unquote(urlsplit(terminal['url']).path)
 if path=='/search':
  candidates=[r for r in validated if r['page']['url']==terminal['url']]
  result['matching_native_result_or_observed_post']=bool(candidates)
  return _judgment(result)
 m=re.fullmatch(r'/f/([^/]+)/([1-9][0-9]*)(?:/[^/]+)?',path)
 target=next((r for r in private['matching_posts']if m and r['id']==int(m[2])and r['forum']==m[1]and r['visibility']=='visible'),None)
 actual=next((r for r in reversed(observations)if r.get('page',{}).get('url')==terminal['url']),None)
 posts=actual.get('native',{}).get('submissions',[])if actual else[]
 result['correct_native_post_title_and_identity']=bool(target and actual and len(posts)==1 and posts[0].get('ids')==[str(target['id'])]and posts[0].get('visible')is True and public.norm(posts[0].get('title'))==public.norm(target['title'])and public.norm(terminal.get('title'))==public.norm(target['title']))
 witness=False
 if target:
  refs={(r['kind'],str(r['id'])):r for r in private['search_rows']}
  for row in validated:
   entry=next((r for r in row['search']['entries']if r.get('kind')=='submission'and r.get('id')==str(target['id'])),None)
   native=refs.get(('submission',str(target['id'])))
   label=search.rendered_search_title(native['highlighted_title'])if native else''
   if entry and label and public.norm(label)in public.norm(row['actual_issued_ax']):witness=True
 result['selected_post_was_in_issued_matching_search']=witness
 result['matching_native_result_or_observed_post']=result['correct_native_post_title_and_identity']and witness
 return _judgment(result)
def _judgment(checks):
 success=all(checks.values());return {'version':VERSION,'status':'success'if success else'failure','reward':float(success),'checks':checks,'private_reference_values_provided':False}

def require_admission(c,p):
 enabled(c)
 if p.get('version')!=PROOF or p.get('fingerprint')!=fingerprint(c)or p.get('source_binding')!=binding(c)or p.get('provenance')!=provenance()or p.get('actor_attempts')!=0 or p.get('api_calls')!=0:raise ValueError('Actual frozen source-bound search proof required')
 cycles=p.get('cycles',[])
 if len(cycles)!=2 or any(not isinstance(r.get('fresh_instance_id'),str)or not re.fullmatch('[0-9a-f]{64}',r['fresh_instance_id'])for r in cycles)or len({r.get('fresh_instance_id')for r in cycles})!=2:raise ValueError('Two independent native cold cycles required')
 baseline=None;private=None
 for cycle in cycles:
  before=validate_complete_snapshot(cycle['complete13_before']);after=validate_complete_snapshot(cycle['complete13_after'])
  if cycle['group_final_seal']is not True or before!=after or cycle['selected_before']!=cycle['selected_after']:raise ValueError('Complete native read-only cold reset proof required')
  if baseline is not None and baseline!=before or private is not None and private!=cycle['private_reference']:raise ValueError('Native baselines/reference differ across fresh sites')
  baseline=before;private=cycle['private_reference'];controls=cycle['controls']
  if set(controls)!=set(EXPECTED):raise ValueError('All result/post and wrong/missing-search controls required')
  for name,record in controls.items():
   if record['judgment']['status']!=EXPECTED[name]or record['integrity']is not True or record['actual_normal_browsergym_session']is not True or record['bound_original_start_restored']is not True or record.get('guard_scope')!='normal_source_full13_before_after' or record['lifecycle']!=shared.METHODS[:-1]or record['provenance']!=provenance():raise ValueError('Actual common-hook lifecycle controls required')
   if validate_complete_snapshot(record['actual_complete13_before'])!=before or validate_complete_snapshot(record['actual_complete13_after'])!=before:raise ValueError('Full guard at every actual preparation/terminal required')
   if evaluate(c,private,record['observations'],record['terminal'],site_origin=record['site_origin'])!=record['judgment']:raise ValueError('Terminal search control re-evaluation differs')
 return deepcopy(baseline),deepcopy(private)

class _SearchHooks(shared._ReadingHooks):
 # Reuse current common attach/initial/record/issued/terminal/trace/close methods.
 def __init__(self,c,baseline,private,directory):
  enabled(c);self.contract=deepcopy(c);self.baseline=deepcopy(validate_complete_snapshot(baseline));self.expected=deepcopy(private);self.directory=Path(directory);self.prepared=False;self.context=None;self.initial=None;self.site=None;self.scored=False;self.events=[];self.observations=[];self.snapshots=[];self.pending=None;self.answer=None
 def prepare(self,site,username):
  if self.prepared or site.domain!='reddit':raise ValueError('One bound actual native prepare required')
  current=shared.protection.complete_snapshot(site,self.directory/'full13-before-progress.jsonl');self.actual_before=deepcopy(current)
  private=reference(site,self.contract,username)
  if current!=self.baseline or private!=self.expected:raise ValueError('Actual complete native baseline/reference differs')
  self.site,self.username,self.selected=site,username,site.fingerprint();self.prepared=True;self.events.append('prepare')
  atomic_write_json(self.directory/'actual-complete13-before.json',current)
 def score_terminal(self,site,terminal,*,runtime_error=None):
  if self.scored or site is not self.site or terminal!=getattr(self,'terminal',None):raise ValueError('Only one actual terminal judgment required')
  self.scored=True;self.events.append('score_terminal')
  result=evaluate(self.contract,self.expected,self.observations,terminal,site_origin=site.url)
  after=shared.protection.complete_snapshot(site,self.directory/'full13-after-progress.jsonl')
  integrity=after==self.baseline and site.fingerprint()==self.selected and reference(site,self.contract,self.username)==self.expected
  if runtime_error:result={'version':VERSION,'status':'unknown','reward':None,'checks':{}}
  elif not integrity:result={'version':VERSION,'status':'failure','reward':0.0,'checks':{'complete_native_integrity':False}}
  self.receipt={'lifecycle':list(dict.fromkeys(self.events)),'provenance':provenance(),'site_origin':site.url,'observations':deepcopy(self.observations),'terminal':deepcopy(terminal),'judgment':result,'integrity':integrity,'guard_scope':'normal_source_full13_before_after','actual_complete13_before':deepcopy(self.actual_before),'actual_complete13_after':deepcopy(after)}
  atomic_write_json(self.directory/'actual-complete13-after.json',after);atomic_write_json(self.directory/'normal-native-search-receipt.json',self.receipt)
  return result,integrity
class SearchCompletionHooks(_SearchHooks):
 def __init__(self,c,proof,directory):
  baseline,private=require_admission(c,proof);super().__init__(c,baseline,private,directory)
def feedback(j):return shared.feedback(j)
