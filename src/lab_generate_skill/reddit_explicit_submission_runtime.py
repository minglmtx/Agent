"""Normal terminal-only lifecycle for the four explicit submission goals.

The existing exact-text/draft evaluator is retained. Original full native vote
rows stay protected; only a declared new post's native author upvote is allowed.
No actor actions or progress-time completion decisions are generated.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,re
from lab_generate_skill import reddit_explicit_submission as rule
from lab_generate_skill.reddit_exact_forum_runtime import protected_snapshot
from lab_generate_skill.reddit_protected_chunks import require_restored_proof,validate_snapshot
from lab_generate_skill.site_database import select_rows
from lab_generate_skill.io_utils import atomic_write_json

VERSION='reddit-explicit-submission-normal-native-v1'
AUTHORIZED_TARGET_WRITES=True


def enabled(c):
 if 'explicit_submission'not in c or 'reviewed_reddit_family' in c:return False
 rule.validate_contract(c)
 if c.get('eligible_for_training')is not False or any(c.get(k)for k in('submission','query','preferences','membership','wiki','vote','reddit_native_read','gitlab_native_read','preference_goal_state','gitlab_navigation_goal')):raise ValueError('Exactly one isolated explicit-submission lifecycle required')
 return True


def require_admission(c,proof):
 enabled(c);rule.require_admission(c,proof);require_restored_proof(proof)
 if proof.get('actor_attempts')!=0:raise ValueError('No-model exact controls required')
 return deepcopy(proof['cycles'][0]['initial_state'])


def bind_normal_contract(original,*,admission_path):
 enabled(original)
 if any(k in original for k in('completion','runtime_version','shared_runtime_ready','admission_result')):raise ValueError('Original CPU contract required')
 c=deepcopy(original);c.update(completion={},runtime_version=VERSION,shared_runtime_ready=False,admission_result=str(admission_path));return c


def require_original_binding(c,original,inventory):
 if bind_normal_contract(original,admission_path=c.get('admission_result',''))!=c:raise ValueError('Only the declared normal compatibility transform is permitted')
 if not isinstance(inventory,dict)or inventory.get('domain')!='reddit'or inventory.get('task_id')!=c['source_task_id']or inventory.get('heldout_quarantine')is not False:raise ValueError('Actual nonheldout source required')
 for key in('source_trace_ids','recorded_start_urls'):
  if c.get(key)!=inventory.get(key):raise ValueError('Original source provenance changed '+key)
 if c.get('original_goal')!=inventory.get('goal'):raise ValueError('Original source goal changed')
 def path(u):
  p=urlsplit(u);return(p.path or'/')+('?' +p.query if p.query else'')+('#'+p.fragment if p.fragment else'')
 starts=list(map(path,inventory['recorded_start_urls']))
 if c.get('recorded_start_paths')!=starts:raise ValueError('Recorded starts changed')
 if c['start_path']!=starts[0]:
  rev=c.get('start_revision',{})
  if rev.get('version')!=1 or rev.get('original_start')!=starts[0]or rev.get('derived_start')!=c['start_path']or not rev.get('reason'):raise ValueError('Start revision missing')
 elif c.get('start_revision'):raise ValueError('Spurious start revision')
 rev=c.get('goal_revision',{})
 if rev.get('version')!=1 or rev.get('original_goal')!=inventory['goal']or rev.get('derived_goal')!=c['goal']or not rev.get('reason'):raise ValueError('Exact declared deterministic training revision required')


def _excluded_id(added):
 if len(added)!=1:return None
 row=added[0]
 ident=row.get('id')
 if type(ident)is not int or ident<=0:raise ValueError('One actual persisted post ID required')
 return ident


def old_vote_snapshot(site,*,new_post_id=None,out=None):
 """Full original vote rows and every additional unrelated vote stay hashed.

Only votes attached to the one actually new post can leave this digest. Every
excluded row is captured in full and checked by native_author_vote(). Neither
old IDs nor old rows are sampled; SQL statements keep the existing 20s budget.
 """
 if new_post_id is not None and(type(new_post_id)is not int or new_post_id<=0):raise ValueError('Exact one native new post required')
 exclude=''if new_post_id is None else' AND submission_id<>'+str(new_post_id)
 count=select_rows(site,'SELECT count(*) AS n FROM submission_votes WHERE true'+exclude)[0]['n'];last=0;covered=0;chunks=0;digest=hashlib.md5()
 if type(count)is not int or count<0:raise ValueError('Exact vote coverage required')
 while covered<count:
  rows=select_rows(site,'SELECT id,md5(row_to_json(r)::text) AS row_md5 FROM submission_votes r WHERE id>'+str(last)+exclude+' ORDER BY id LIMIT 2048')
  if len(rows)!=min(2048,count-covered):raise ValueError('Full original vote chunk coverage changed')
  for r in rows:
   if set(r)!={'id','row_md5'}or type(r['id'])is not int or r['id']<=last or not isinstance(r['row_md5'],str)or not re.fullmatch('[0-9a-f]{32}',r['row_md5']):raise ValueError('Exact indexed vote row coverage required')
   digest.update(r['row_md5'].encode());last=r['id']
  covered+=len(rows);chunks+=1
  if out:
   with Path(out).open('a')as f:f.write(__import__('json').dumps({'table':'submission_votes','covered':covered,'total':count,'chunks':chunks,'statement_timeout_seconds':20})+'\n')
 if select_rows(site,'SELECT count(*) AS n FROM submission_votes WHERE true'+exclude)[0]['n']!=count:raise ValueError('Vote state changed during full capture')
 added=[]if new_post_id is None else select_rows(site,'SELECT * FROM submission_votes WHERE submission_id='+str(new_post_id)+' ORDER BY id')
 return {'original':{'count':count,'digest':digest.hexdigest()},'new_post_votes':added,'excluded_only_new_post_id':new_post_id}


def native_author_vote(votes,post,user):
 if post is None:return votes==[]
 if len(votes)!=1:return False
 r=votes[0]
 # The native Submission constructor makes exactly this author upvote. We
 # inspect every row/column; metadata must have its genuine native types.
 if set(r)!={'id','upvote','timestamp','user_id','ip','submission_id'}or type(r.get('id'))is not int or r['id']<=0 or r.get('upvote')is not True or r.get('user_id')!=user or r.get('submission_id')!=post:return False
 if not isinstance(r.get('timestamp'),str):return False
 try:stamp=datetime.fromisoformat(r['timestamp'].replace('Z','+00:00'))
 except ValueError:return False
 if stamp.tzinfo is None:return False
 if r['ip']is not None:
  try:__import__('ipaddress').ip_address(r['ip'])
  except ValueError:return False
 return True


def protection_integrity(before,after,votes,*,kind,added,user):
 validate_snapshot(before);validate_snapshot(after)
 post=_excluded_id(added)if kind=='published_text'else None
 if votes.get('excluded_only_new_post_id')!=post:raise ValueError('Excluded votes belong to a different scope')
 allowed=native_author_vote(votes['new_post_votes'],post,user)
 # All eleven other native tables remain exact, including comment votes,
 # users, forums and all ownership/subscription relations.
 untouched=all(before[t]==after[t]for t in before if t!='submission_votes')
 return untouched and votes['original']==before['submission_votes']and allowed


class ExplicitSubmissionHooks:
 def __init__(self,c,proof,directory):
  self.initial=require_admission(c,proof);self.contract,self.proof=deepcopy(c),deepcopy(proof);self.directory=Path(directory);self.prepared=self.scored=False;self.context=self.initial_page=None;self.public=None
 def prepare(self,site,username):
  if self.prepared:raise ValueError('One fresh native submission baseline required')
  state=rule.state(site,username);rule.validate_initial(self.contract,state);protected=protected_snapshot(site)
  if state!=self.initial or protected!=self.proof['cycles'][0]['private_protected_before']or site.fingerprint()!=self.proof['cycles'][0]['initial_fingerprint']:raise ValueError('Actual native baseline differs from both exact CPU controls')
  self.site,self.username,self.before=site,username,protected;self.prepared=True;atomic_write_json(self.directory/'explicit-submission-baseline.json',{'state':state,'full12':protected})
 def attach(self,context):
  if not self.prepared or self.context is not None:raise ValueError('One prepared browser context required')
  self.context=context
 def observe_initial(self,page):
  if self.initial_page is not None or page.context is not self.context:raise ValueError('One bound initial page required')
  actual=urlsplit(page.url);start=urlsplit(self.contract['start_path']);origin=urlsplit(self.site.url)
  if (actual.scheme,actual.netloc)!=(origin.scheme,origin.netloc)or(actual.path,actual.query,actual.fragment)!=(start.path,start.query,start.fragment):raise ValueError('Declared task start changed')
  self.initial_page=page
 def capture_terminal(self,page,terminal):
  if self.initial_page is None or page.context is not self.context:raise ValueError('Bound terminal browser required')
  self.public=page.evaluate(rule.READ);terminal['explicit_submission_terminal_public']=deepcopy(self.public)
 def score_terminal(self,site,page,*,runtime_error=None):
  if not self.prepared or self.scored or site is not self.site:raise ValueError('One terminal judgment required')
  self.scored=True;final=protected=votes=None
  try:
   final=rule.state(site,self.username,self.initial);protected=protected_snapshot(site);kind=self.contract['explicit_submission']['kind'];post=_excluded_id(final['added'])if kind=='published_text'else None
   votes=old_vote_snapshot(site,new_post_id=post,out=self.directory/'explicit-original-vote-progress.jsonl');integrity=protection_integrity(self.before,protected,votes,kind=kind,added=final['added'],user=self.initial['user_id'])
   j=rule.evaluate(self.contract,page,self.initial,final,site_origin=site.url,public=self.public,runtime_error=runtime_error);j['version']=VERSION;j['checks']['complete_native_non_target_records_unchanged']=integrity
   if j['status']!='unknown'and not integrity:j.update(status='failure',reward=0.)
  except Exception as exc:
   integrity=False;j={'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Complete native terminal capture unavailable','exception_type':type(exc).__name__}
  atomic_write_json(self.directory/'explicit-submission-terminal-state.json',{'state':final,'full12_before':self.before,'full12_after':protected,'full_original_vote_scope':votes,'public_terminal':self.public,'judgment':j,'terminal_only':True})
  return j,integrity
 def close(self):pass


def feedback(j):
 return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),'checks':[{'name':k,'passed':v,'condition':k.replace('_',' ')+'.'}for k,v in j.get('checks',{}).items()],'action_sequence_provided':False,'private_reference_values_provided':False}
