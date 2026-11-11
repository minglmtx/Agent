"""Candidate complete forum-name query and native Top/period viewing.

All observations and terminal checks reuse native readers and full13 protection.
The interface does not invent a search date filter, navigation action, answer
or category taxonomy. Normal admission remains an actual two-cold gate.
"""
from copy import deepcopy
from datetime import datetime
import hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit,unquote
from . import reddit_final_read_runtime as shared
from . import reddit_forum_list as forums
from . import reddit_post_list as posts
from .reddit_native_read_runtime import validate_complete_snapshot
from .source_revision_binding import binding,fingerprint,require_source_binding
from .site_navigation_rules import valid_initial_page
from .site_database import select_rows
from .io_utils import atomic_write_json

VERSION='reddit-public-native-reading-bridge-v1'
PROOF='reddit-public-native-reading-bridge-two-cold-v1'
FORUM_MARKERS=r'''() => {
 const root=document.querySelector('#main');
 const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 return root?[...root.querySelectorAll('a[href]')].filter(e=>visible(e)&&/^\/f\/[^/]+$/.test(new URL(e.href).pathname))
 .map(e=>({path:new URL(e.href).pathname,label:e.innerText.trim().replace(/\s+/g,' '),bid:e.getAttribute('bid')})):[];
}'''


def enabled(c):
    if 'reddit_reading_bridge'not in c:return False
    binding(c);s=c['reddit_reading_bridge']
    if (c.get('domain')!='reddit' or c.get('eligible_for_training')is not False
            or s.get('kind')not in ('all_forum_names','forum_top_period')
            or any(c.get(k)for k in ('parented_reply','reddit_original_reading','reddit_maximum_query','reddit_search_completion','query','preferences','explicit_submission','membership'))):
        raise ValueError('One explicit read-only native bridge required')
    expected={'all_forum_names':{'kind'},'forum_top_period':{'kind','forum','sort','time_window'}}[s['kind']]
    if set(s)!=expected:raise ValueError('Exact public native reading scope required')
    if s['kind']=='forum_top_period':
        p=c.get('public_parameters',{})
        if (s['sort']!='top' or s['time_window']!='year' or not re.fullmatch('[A-Za-z0-9_]+',s['forum'])
                or any(p.get(k)!=s[k]for k in ('forum','sort','time_window'))
                or p.get('clock_policy')!='native_current_at_capture'):
            raise ValueError('Native forum Top/Past year and public clock policy required')
        clock=datetime.fromisoformat(p.get('clock_reference_utc','').replace('Z','+00:00'))
        if clock.tzinfo is None:raise ValueError('Public aware UTC clock context required')
    if c.get('public_task_input')!={'goal':c['goal'],'public_parameters':c.get('public_parameters')}:
        raise ValueError('All required parameters must reach generator and actor')
    return True


def fields(c):enabled(c);return ['items']if c['reddit_reading_bridge']['kind']=='all_forum_names'else[]
def public_goal(c):
    enabled(c);goal=c['goal']+'\nPublic task parameters: '+json.dumps(c['public_parameters'],sort_keys=True)
    if fields(c):
        from .browser_prompt_contract import query_finish_instruction
        goal+='\n'+query_finish_instruction(['items'])+'\nitems must be an array of objects, each with one name string.'
    return goal
def require_original_binding(c,original,inventory):return require_source_binding(c,original,inventory,domain='reddit')
def provenance():
    return dict(shared.provenance(),reading_bridge_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                native_forum_list_sha256=hashlib.sha256(Path(forums.__file__).read_bytes()).hexdigest(),
                native_post_list_sha256=hashlib.sha256(Path(posts.__file__).read_bytes()).hexdigest())
def reference(site,c,username):
    enabled(c)
    if c['reddit_reading_bridge']['kind']=='all_forum_names':
        users=select_rows(site,"SELECT id,username FROM users WHERE username='"+username.replace("'","''")+"'")
        if len(users)!=1:raise ValueError('One native account required')
        return {'account':users[0],'forum_reference':forums.forum_reference(site,include_default_views=True)}
    return posts.post_reference(site,c['reddit_reading_bridge']['forum'],username)


def _evaluate(c,private,observations,terminal,answer,*,site_origin):
    enabled(c);s=c['reddit_reading_bridge']
    checks={'terminal_native_document_valid':valid_initial_page(terminal,site_origin=site_origin)}
    if not checks['terminal_native_document_valid']:return _judgment(checks)
    valid=[r for r in observations if isinstance(r,dict)and valid_initial_page(r.get('page'),site_origin=site_origin)
           and r.get('native',{}).get('url')==r['page']['url']and isinstance(r.get('actual_issued_ax'),str)]
    if s['kind']=='forum_top_period':
        current=next((r for r in reversed(valid)if r['page']['url']==terminal['url']),None)
        if current is None:return _judgment(checks|{'issued_terminal_native_list':False})
        state=current.get('post_list')
        if not isinstance(state,dict):return _judgment(checks|{'issued_terminal_native_list':False})
        # This is precisely the installed native captured-UTC/cutoff/cursor
        # logic, including its five-second boundary-uncertainty safeguard.
        checks.update(posts.post_list_checks({'forum':s['forum'],'allowed_sorts':['top'],'allowed_times':['year'],'reference':private},state,terminal['url']))
        return _judgment(checks)
    ref=private['forum_reference'];known={r['name']:r for r in ref['rows']};witnessed=set();directory=False
    for row in valid:
        if 'forum_list'not in row:continue
        result=forums.forum_list_checks({'mode':'browse','reference':ref},row['forum_list'],row['page']['url'])
        if not result or not all(result.values()):continue
        directory=True
        for entry in row.get('forum_markers',[]):
            name=unquote(entry.get('path','')).removeprefix('/f/');bid=entry.get('bid')
            if name in known and isinstance(bid,str)and '['+bid+']'in row['actual_issued_ax']:
                witnessed.add(name)
    try:reply=json.loads(answer)if isinstance(answer,str)else answer
    except ValueError:reply=None
    items=reply.get('items')if isinstance(reply,dict)and set(reply)=={'items'}else None
    names=[r['name']for r in items]if isinstance(items,list)and all(isinstance(r,dict)and set(r)=={'name'}and isinstance(r['name'],str)for r in items)else None
    checks.update(correct_native_directory_observed=directory,complete_names_in_issued_observations=witnessed==set(known),
                  complete_typed_forum_names=names is not None and len(names)==len(set(names))and set(names)==set(known))
    return _judgment(checks)
def evaluate(c,private,observations,terminal,answer,*,site_origin):
    try:return _evaluate(c,private,observations,terminal,answer,site_origin=site_origin)
    except (ValueError,TypeError,KeyError)as error:
        return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Complete native reading capture unavailable','private_diagnostic':type(error).__name__}

def _judgment(checks):
    success=all(checks.values());return {'version':VERSION,'status':'success'if success else'failure','reward':float(success),'checks':checks,'private_reference_values_provided':False}


def expected_controls(c):
    enabled(c)
    return {'initial_no_op':'failure','positive':'success','wrong_target':'failure','404':'failure','login':'failure','partial_collection':'failure'}


def require_admission(c,p):
    enabled(c)
    if (not isinstance(p,dict)or p.get('version')!=PROOF or p.get('fingerprint')!=fingerprint(c)
            or p.get('source_binding')!=binding(c)or p.get('provenance')!=provenance()
            or p.get('actor_attempts')!=0 or p.get('api_calls')!=0):
        raise ValueError('Exact actual native reading-bridge source proof required')
    cycles=p.get('cycles',[])
    if len(cycles)!=2 or any(not isinstance(r.get('fresh_instance_id'),str)or not re.fullmatch('[0-9a-f]{64}',r['fresh_instance_id'])for r in cycles)or len({r['fresh_instance_id']for r in cycles})!=2:
        raise ValueError('Two independent native cold instances required')
    baseline=private=None
    for cycle in cycles:
        before=validate_complete_snapshot(cycle['complete13_before']);after=validate_complete_snapshot(cycle['complete13_after'])
        if (cycle['group_final_seal']is not True or before!=after or cycle['selected_before']!=cycle['selected_after']
                or baseline is not None and baseline!=before or private is not None and private!=cycle['private_reference']):
            raise ValueError('Actual complete native cold-group reset/reference required')
        baseline=before;private=cycle['private_reference'];controls=cycle['controls']
        if set(controls)!=set(expected_controls(c)):raise ValueError('Complete native reading positive/negative controls required')
        for name,row in controls.items():
            if (row.get('actual_normal_browsergym_session')is not True or row.get('bound_original_start_restored')is not True
                    or row.get('lifecycle')!=shared.METHODS[:-1]or row.get('provenance')!=provenance()
                    or row.get('guard_scope')!='normal_source_full13_before_after' or row.get('integrity')is not True
                    or validate_complete_snapshot(row['actual_complete13_before'])!=baseline
                    or validate_complete_snapshot(row['actual_complete13_after'])!=baseline):
                raise ValueError('Fresh full13 every actual ordinary preparation and terminal required')
            reproduced=evaluate(c,private,row['observations'],row['terminal'],row['answer'],site_origin=row['site_origin'])
            if row['judgment']!=reproduced or reproduced['status']!=expected_controls(c)[name]:raise ValueError('Actual native reading terminal does not reproduce')
    return deepcopy(baseline),deepcopy(private)


class _BridgeHooks(shared._ReadingHooks):
    def __init__(self,c,baseline,private,directory):
        enabled(c);self.contract=deepcopy(c);self.baseline=deepcopy(validate_complete_snapshot(baseline));self.expected=deepcopy(private)
        self.directory=Path(directory);self.epoch=None;self.prepared=False;self.context=self.initial=self.site=None
        self.scored=False;self.events=[];self.observations=[];self.snapshots=[];self.pending=None;self.answer=None
    def prepare(self,site,username):
        if self.prepared or site.domain!='reddit':raise ValueError('One actual native preparation required')
        current=shared.protection.complete_snapshot(site,self.directory/'full13-before-progress.jsonl')
        private=reference(site,self.contract,username)
        if current!=self.baseline or private!=self.expected:raise ValueError('Actual full13/native reference differs')
        self.actual_before=deepcopy(current);self.site,self.username,self.selected=site,username,site.fingerprint();self.prepared=True;self.events.append('prepare')
        atomic_write_json(self.directory/'actual-complete13-before.json',current)
    def record(self,page):
        super().record(page)
        current=self.pending['original'];path=urlsplit(page.url).path
        if re.fullmatch('/forums(?:/all|/by_(?:name|title|creation_date|submissions|subscribers)(?:/[1-9][0-9]*)?|/[1-9][0-9]*)?',path):
            current['forum_list']=forums.read_forum_list(page);current['forum_markers']=page.evaluate(FORUM_MARKERS)
        if re.fullmatch('/f/[^/]+(?:/(?:hot|new|top|most_commented))?/?',path):current['post_list']=posts.read_post_list(page)
    def score_terminal(self,site,terminal,*,runtime_error=None):
        if self.scored or site is not self.site or terminal!=getattr(self,'terminal',None):raise ValueError('Only actual bound terminal scoring allowed')
        self.scored=True;self.events.append('score_terminal')
        result=evaluate(self.contract,self.expected,self.observations,terminal,self.answer,site_origin=site.url)
        after=shared.protection.complete_snapshot(site,self.directory/'full13-after-progress.jsonl')
        integrity=after==self.baseline and site.fingerprint()==self.selected and reference(site,self.contract,self.username)==self.expected
        if runtime_error:result={'version':VERSION,'status':'unknown','reward':None,'checks':{}}
        elif not integrity:result={'version':VERSION,'status':'failure','reward':0.0,'checks':{'complete_native_integrity':False}}
        self.receipt={'lifecycle':list(dict.fromkeys(self.events)),'provenance':provenance(),'site_origin':site.url,'observations':deepcopy(self.observations),'snapshots':deepcopy(self.snapshots),'terminal':deepcopy(terminal),'answer':self.answer,'judgment':result,'integrity':integrity,'guard_scope':'normal_source_full13_before_after','actual_complete13_before':deepcopy(self.actual_before),'actual_complete13_after':deepcopy(after)}
        atomic_write_json(self.directory/'normal-native-reading-bridge-receipt.json',self.receipt);return result,integrity
class ReadingBridgeHooks(_BridgeHooks):
    def __init__(self,c,proof,directory):
        baseline,private=require_admission(c,proof);super().__init__(c,baseline,private,directory)
def create_cpu_hooks(c,baseline,private,directory,*,cpu_control_only=False):
    if cpu_control_only is not True:raise ValueError('Unadmitted constructor is CPU control only')
    from .runtime_watchdog import require_watchdog
    require_watchdog();return _BridgeHooks(c,baseline,private,directory)
def feedback(j):return shared.feedback(j)
