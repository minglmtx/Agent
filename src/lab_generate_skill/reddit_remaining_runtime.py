"""Native Reddit terminal completion, with private references and issued AX proof.

CPU normal controls remain distinct from runtime readiness. No evaluator runs in
an intermediate observation, and no reference/expected output enters actor input.
"""
import copy,hashlib,json,re
from urllib.parse import quote,urlsplit,unquote
from zoneinfo import ZoneInfo
from . import reddit_remaining_normal as normal
from .site_database import select_rows
from .reddit_forum_list import forum_reference
from .reddit_search import search_reference
from .browser_http_status import terminal_document_evidence,is_error_document
from .browser_prompt_contract import query_finish_instruction
from .io_utils import atomic_write_json
from .site_result_guard import guard_site_result
from .public_read_memory import PublicReadMemory,IssuedPublicReadActor,PublicReadProtocol,metadata_line,render_snapshot

VERSION='reddit-native-issued-ax-runtime-v1'
ADMISSION_VERSION='reddit-native-normal-admission-v1'
NORMAL_VERSION='reddit-remaining-sixteen-native-normal-controls-v1'
FIELDS={'dated_comments':'comments','public_imported_identifier':'identifier','forum_name_search':'forum_names','search_scope_count':'count','search_scope_posts':'post_ids','search_scope_all_posts':'post_ids'}
KINDS=set(FIELDS)|{'user_submissions','profile_settings','username_settings','wiki_directory','native_search'}
PUBLIC_READ=r"""() => {
 const own=(e,s)=>[...e.querySelectorAll(s)].filter(n=>n.closest('article')===e);
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const root=document.getElementById('main');if(!root)return [];
 return [...root.querySelectorAll('article.submission,article.comment')].map(e=>{
  const comment=e.classList.contains('comment');
  const label=comment?own(e,'.comment__body')[0]:e.querySelector('.submission__title');
  const links=comment?own(e,'a.comment__permalink'):own(e,'a[href]');
  const time=comment?own(e,'.comment__header time')[0]:e.querySelector('time.submission__timestamp');
  return {kind:comment?'comment':'submission',label:label?.innerText||'',visible:visible(label),
   links:links.filter(visible).map(a=>a.href),timestamp:time?.dateTime||'',displayed_time:time?.title||''};
 });
}"""
MARKER='Native public record: '


def enabled(contract):
    value=contract.get('reddit_native_task')
    if value is None:return False
    if contract.get('domain')!='reddit' or not isinstance(value,dict)or value.get('kind')not in KINDS:
        raise ValueError('One supported native Reddit task family required')
    if any(contract.get(k)for k in ('query','membership','preferences','forum_creation','submission','wiki','search')):
        raise ValueError('Native read-only family cannot mix another task profile')
    return True


def answer_fields(contract):
    if not enabled(contract):return None
    field=FIELDS.get(contract['reddit_native_task']['kind'])
    return [field]if field else None


def public_goal(contract):
    if not enabled(contract):return contract['goal']
    fields=answer_fields(contract)
    if not fields:return contract['goal']
    field=fields[0]
    shapes={'comments':'comments is an array of objects with exactly body (displayed text) and timestamp (the native ISO8601 time). Include every requested comment, or [] when none match.',
      'identifier':'identifier is the exact publicly displayed imported identifier string.',
      'forum_names':'forum_names is an array of requested native forum-name strings.',
      'count':'count is an integer count of the requested native result entries, including both posts and comments.',
      'post_ids':'post_ids is an array of positive numeric post identifiers from the public /f/<forum>/<post-id>/... record URLs. Use the actual visible record link; hidden DOM vote attributes are not an answer source.'}
    # Replace the general record-ID string guidance for this site's explicitly
    # numeric public Postmill path IDs; there is no private expected value here.
    protocol=query_finish_instruction(fields).replace('Record identifiers are exact strings: preserve all leading zeros; do not convert an ID to a number.','')
    return contract['goal']+'\n'+protocol+' '+shapes[field]


def _one(rows):
    if not isinstance(rows,list)or len(rows)!=1:raise ValueError('One actual native account required')
    return rows[0]


def reference(site,auth,contracts):
    """Private SQL only, matching the independent normal-control reference."""
    if any(not enabled(c)for c in contracts):raise ValueError('Dedicated native read-only contracts required')
    cols=select_rows(site,"SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('users','forums','comments') ORDER BY table_name,column_name")
    public_fields=[f for f in ('biography','bio','reddit_id','reddit_user_id','source_id')if f in{r['column_name']for r in cols if r['table_name']=='users'}]
    names=','.join("'"+s.replace("'","''")+"'"for s in (auth['username'],'GetFreeCash','7SlotGrill'))
    users=select_rows(site,'SELECT id,username,timezone'+(' ,'+','.join(public_fields)if public_fields else '')+' FROM users WHERE username IN ('+names+') ORDER BY id')
    if len(users)!=3 or len({r['username']for r in users})!=3:raise ValueError('Native requested accounts missing or ambiguous')
    viewer=_one([r for r in users if r['username']==auth['username']]);ZoneInfo(viewer['timezone'])
    if type(viewer['id'])is not int or viewer['id']<=0:raise ValueError('Exact native viewer identifier required')
    exact={'schema':cols,'users':users,'public_identifier_fields':public_fields,
      'forums':select_rows(site,"SELECT id,name,description,sidebar FROM forums WHERE name IN ('AskReddit','Music','movies') ORDER BY id"),
      'submissions':select_rows(site,"SELECT s.id,s.user_id,s.title,s.timestamp,s.visibility,f.name AS forum,u.username FROM submissions s JOIN users u ON u.id=s.user_id JOIN forums f ON f.id=s.forum_id WHERE u.username='GetFreeCash' ORDER BY s.id"),
      'comments':select_rows(site,"SELECT c.id,c.submission_id,c.user_id,c.body,c.timestamp,c.visibility,s.title AS submission_title,s.visibility AS submission_visibility,f.name AS forum,u.username FROM comments c JOIN users u ON u.id=c.user_id JOIN submissions s ON s.id=c.submission_id JOIN forums f ON f.id=s.forum_id WHERE u.username='7SlotGrill' ORDER BY c.id"),
      'viewer_username':auth['username'],'viewer_timezone':viewer['timezone'],
      'viewer_blocks':select_rows(site,f"SELECT blocker_id,blocked_id FROM user_blocks WHERE blocker_id={viewer['id']} ORDER BY blocked_id")}
    searches={}
    for query in sorted({c['reddit_native_task']['query']for c in contracts if'query'in c['reddit_native_task']}):
        rows=search_reference(site,query);scope=[]
        for kind,table in [('submission','submissions'),('comment','comments')]:
            ids=[r['id']for r in rows if r['kind']==kind]
            if any(type(i)is not int or i<=0 for i in ids):raise ValueError('Exact native search identities required')
            if not ids:continue
            join='JOIN forums f ON f.id=e.forum_id'if kind=='submission'else'JOIN submissions s ON s.id=e.submission_id JOIN forums f ON f.id=s.forum_id'
            scope+=select_rows(site,"SELECT '"+kind+"' AS kind,e.id,f.name AS forum FROM "+table+' e '+join+' WHERE e.id IN ('+','.join(map(str,ids))+') ORDER BY e.id')
        if{(r['kind'],r['id'])for r in scope}!={(r['kind'],r['id'])for r in rows}:raise ValueError('Independent actual result relation missing')
        searches[query]={'search_rows':rows,'scope_rows':sorted(scope,key=lambda r:(r['kind'],r['id']))}
    return {'exact':exact,'forum_reference':forum_reference(site),'searches':searches}


def specification(contract,ref):
    if not enabled(contract):raise ValueError('Native task required')
    spec=copy.deepcopy(contract['reddit_native_task']);kind=spec['kind'];exact=ref['exact'];username=spec.get('username',exact['viewer_username']);user=_one([r for r in exact['users']if r['username']==username])
    common={'username':username,'timezone':exact['viewer_timezone'],'biography':user.get('biography')}
    if kind=='dated_comments':common['rows']=[r for r in exact['comments']if r['username']==username]
    elif kind=='user_submissions':common['rows']=[r for r in exact['submissions']if r['username']==username]
    elif kind=='public_imported_identifier':common['public_identifier']=user['biography']
    elif kind=='forum_name_search':common['forum_reference']=ref['forum_reference']
    elif'query'in spec:common.update(ref['searches'][spec['query']])
    spec['reference']=common
    return spec


def public_record(row,origin):
    """Read an identity from an actual public permalink, never data-vote-id."""
    if not isinstance(row,dict)or row.get('kind')not in('comment','submission')or not isinstance(row.get('label'),str)or not isinstance(row.get('links'),list):raise ValueError('Native public record link required')
    found=[]; rejected_origin=False
    for link in row['links']:
        if not isinstance(link,str):raise ValueError('Actual public link string required')
        # A native submission title can point outside this website. Its visible
        # same-article comments/permalink link remains the public identity source.
        # Filter candidate links; never follow them or read hidden vote IDs.
        try:path=normal._path(link,origin).split('?',1)[0].split('#',1)[0]
        except (ValueError,TypeError):
            rejected_origin=True;continue
        pattern=r'/f/[^/]+/[1-9][0-9]*/-/comment/([1-9][0-9]*)'if row['kind']=='comment'else r'/f/[^/]+/([1-9][0-9]*)(?:/[^/]*)?'
        m=re.fullmatch(pattern,path)
        if m:found.append((link,int(m[1])))
    if not found and rejected_origin:raise ValueError('Public record permalink must belong to the local site')
    if len({ident for _,ident in found})!=1:raise ValueError('One public record permalink required')
    url,ident=found[0]
    return {'kind':row['kind'],'record_id':ident,'url':url,'label':row['label'],'timestamp':row['timestamp'],'displayed_time':row['displayed_time']}


def public_line(record):
    return metadata_line(record)


def supplement(ax,rows,origin):
    """Metadata only for actual record text present in this AX variant."""
    if not isinstance(ax,str):raise ValueError('Actual AX text required')
    text=normal.norm(ax);public=[]
    for row in rows:
        label=normal.norm(row.get('label',''))
        if row.get('visible')is not True or not label or label not in text:continue
        public.append(public_record(row,origin))
    lines=[public_line(r)for r in public]
    return ax+('\n\nPublic metadata for records in this observation:\n'+'\n'.join(lines)if lines else''),public


def health(page,observed=None):
    http=terminal_document_evidence(page,observed);path=urlsplit(page.url).path;title=page.title()
    return {'url':page.url,'http_status':http['http_status'],'http_status_evidence':http,'title':title,
      'heading_texts':[x.strip()for x in page.locator('h1,h2,h3').all_text_contents()],
      'login_page':path=='/login','error_page':is_error_document(page.url,http['http_status'],title)}


class Collector:
    """Observe only the BrowserGym active page; no goto or private reference."""
    def __init__(self,context,origin,directory):
        self.origin=origin;self.directory=directory;self.visits=[];self.events=normal.UsernameVisits(context);self.memory=PublicReadMemory(origin)
    def reset(self):self.events.reset();self.visits=[];self.memory=PublicReadMemory(self.origin)
    def record(self,page,obs,document_status=None):
        capture=normal.read_page(page,health(page,document_status));rows=page.evaluate(PUBLIC_READ);public=[]
        if page.url!=capture['page']['url']:raise ValueError('Native document changed between public captures')
        for field in('axtree_txt','axtree_full_txt'):
            if field in obs:
                obs[field],values=supplement(obs[field],rows,self.origin)
                obs[field]+=self.memory.render()
                public+=values
        capture['public_memory_at_observation']=self.memory.snapshot()
        capture['public_records']=list({(r['kind'],r['record_id']):r for r in public}.values())
        obs['reddit_native_visit_index']=len(self.visits);self.visits.append(capture);self.save()
        return obs
    def refresh_public_memory(self,observation):
        result=dict(observation)
        if not self.visits:return result
        sample=self.visits[-1];old=render_snapshot(sample['public_memory_at_observation']);new=self.memory.render()
        for field in('axtree_txt','axtree_full_txt'):
            if field in result:
                value=result[field]
                if old and value.endswith(old):value=value[:-len(old)]
                result[field]=value+new
        sample['public_memory_at_observation']=self.memory.snapshot();self.save();return result
    def acknowledge_issued(self,actual_ax):
        if self.visits:
            sample=self.visits[-1];self.memory.acknowledge(actual_ax,sample['public_records'],expected_memory_text=render_snapshot(sample['public_memory_at_observation']));self.save()
    def terminal(self,page,document_status=None):
        capture=normal.read_page(page,health(page,document_status));capture['public_records']=[];self.visits.append(capture);self.save()
        return capture
    def save(self):
        atomic_write_json(self.directory/'reddit-native-visits.json',{'version':VERSION,'observations':self.visits,'username_visits':self.events.snapshot(),'public_read_memory':self.memory.snapshot()})


def _issued_views(trace,observations):
    result={}
    for message in trace.get('messages',[]):
        if message.get('role')!='user':continue
        try:obs=json.loads(message['content'])
        except(ValueError,TypeError,KeyError):continue
        index=obs.get('reddit_native_visit_index')
        if type(index)is not int or not 0<=index<len(observations)or obs.get('observation_record_source')!='actual_actor_request':continue
        saved=observations[index]
        if obs.get('url')!=saved['page']['url']or not isinstance(obs.get('axtree_txt'),str):raise ValueError('Issued native visit identity differs')
        result.setdefault(index,[]).append(obs['axtree_txt'])
    return result


def _issued(trace,observations):
    result={}
    for index,texts in _issued_views(trace,observations).items():
        saved=observations[index];exposed=[]
        for row in saved.get('public_records',[]):
            line=public_line(row)
            if any(line in text and normal.norm(row['label'])in normal.norm(text)for text in texts):exposed.append(row)
        result.setdefault(index,[]).extend(exposed)
    return result


def exposure_checks(spec,observations,trace):
    issued=_issued(trace,observations);kind=spec['kind'];result={'actual_issued_native_observation':bool(issued)}
    if not result['actual_issued_native_observation']:return result
    if kind in('dated_comments','user_submissions'):
        path='/user/'+quote(spec['reference']['username'],safe='')+('/comments'if kind=='dated_comments'else'/submissions')
        needed=set();seen=set()
        for index,obs in enumerate(observations):
            if urlsplit(obs['page']['url']).path!=path:continue
            field='comments'if kind=='dated_comments'else'submissions'
            needed.update((field[:-1],normal._id(row['ids'][0]))for row in obs['native'][field])
            seen.update((r['kind'],r['record_id'])for r in issued.get(index,[]))
        result['complete_listing_records_exposed']=needed<=seen
    elif kind in('search_scope_count','search_scope_all_posts'):
        path=observations[-1]['page']['url'];wanted={(r['kind'],normal._id(r['id']))for r in observations[-1]['native']['scoped']};seen=set()
        for index,rows in issued.items():
            if observations[index]['page']['url']==path:seen.update((r['kind'],r['record_id'])for r in rows)
        result['complete_native_results_exposed']=wanted<=seen
    elif kind=='search_scope_posts':
        wanted={(r['kind'],r['id'])for r in spec['reference']['scope_rows']if r['kind']=='submission'and r['forum']==spec['forum']};seen={(r['kind'],r['record_id'])for rows in issued.values()for r in rows}
        result['requested_public_post_identity_exposed']=bool(wanted&seen)
    if kind in('dated_comments','search_scope_count','search_scope_all_posts'):
        last_index=max(issued);last_text=_issued_views(trace,observations)[last_index][-1];last_sample=observations[last_index];available={(r['kind'],r['record_id'])for r in last_sample.get('public_records',[])if public_line(r)in last_text and normal.norm(r['label'])in normal.norm(last_text)}
        remembered=last_sample.get('public_memory_at_observation')
        if remembered and render_snapshot(remembered).strip()and render_snapshot(remembered).strip()in last_text:
            available.update((r['kind'],r['record_id'])for r in remembered['records'])
        result['complete_information_in_final_request']=(needed if kind=='dated_comments'else wanted)<=available
    if kind=='forum_name_search':
        names=[]
        for obs in observations:
            if 'forum_list'in obs:
                names+=[unquote(urlsplit(e['path']).path).removeprefix('/f/')for e in obs['forum_list']['entries']if spec['term'].casefold()in unquote(urlsplit(e['path']).path).casefold()]
        text='\n'.join(text for index,texts in _issued_views(trace,observations).items()if urlsplit(observations[index]['page']['url']).path=='/forums/all'for text in texts)
        result['requested_forum_names_exposed']=bool(names)and(all(name in text for name in names)if spec['all_matches']else any(name in text for name in names))
    if kind=='public_imported_identifier':
        text='\n'.join(text for index,texts in _issued_views(trace,observations).items()if urlsplit(observations[index]['page']['url']).path=='/user/'+quote(spec['reference']['username'],safe='')for text in texts)
        result['public_identifier_exposed']=spec['reference']['public_identifier']in text
    return result


def _unwrap(contract,answer):
    fields=answer_fields(contract)
    if fields is None:return None,True
    if isinstance(answer,str):
        try:
            from .admin_query_rules import parse_answer
            answer=parse_answer(answer)
        except(ValueError,TypeError):return None,False
    return (answer[fields[0]],True)if isinstance(answer,dict)and set(answer)==set(fields)else(None,False)


def evaluate(contract,stored,trace,initial,final,*,site_origin,answer=None,runtime_error=None):
    if runtime_error:return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Runtime failure prevents terminal scoring'}
    try:
        if stored.get('version')!=VERSION:raise ValueError('Runtime native visit protocol missing')
        if stored['observations'][-1]['page'].get('http_status')is None:raise ValueError('Terminal HTTP document evidence unavailable')
        spec=specification(contract,initial);value,shape=_unwrap(contract,answer)
        memory=stored.get('public_read_memory')
        if memory and memory.get('capture_limited')is True and spec['kind']in('dated_comments','search_scope_count','search_scope_all_posts'):raise ValueError('Bounded public reading memory omitted whole historical records')
        judgment=normal.evaluate(spec,stored['observations'],site_origin=site_origin,answer=value,username_visits=stored['username_visits'])
        if judgment['status']=='unknown':return judgment
        conditions=exposure_checks(spec,stored['observations'],trace);conditions['native_answer_protocol']=shape
        judgment['checks'].update(conditions)
        prior_complete=conditions.get('complete_listing_records_exposed',conditions.get('complete_native_results_exposed'))
        if conditions.get('complete_information_in_final_request')is False and prior_complete is True:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':judgment['checks'],'reason':'Previously observed complete query information was omitted from the final actor request; inspect public memory/context budget'}
        ok=all(judgment['checks'].values());judgment.update(version=VERSION,status='success'if ok else'failure',reward=1. if ok else 0.)
        return guard_site_result(judgment,runtime_error=None,selected_records_unchanged=initial==final)
    except(ValueError,TypeError,KeyError,AttributeError)as exc:
        return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Native runtime capture incomplete: '+str(exc)}


def fingerprint(contract):
    keys=('task_id','source_task_id','domain','goal','original_goal','start_path','recorded_start_paths','source_trace_ids','heldout_quarantine','task_text_changed','is_explicit_derivative','derivation_reason','eligible_for_training','training')
    payload={k:contract.get(k)for k in keys};payload['native_family']=contract.get('reddit_native_task',contract.get('native_family'))
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def require_admission(contract,proof):
    if not enabled(contract)or contract.get('heldout_quarantine')is not False or contract.get('training')is not False or contract.get('eligible_for_training')is not False:raise ValueError('Development-only native task required')
    if proof.get('admission_version')!=ADMISSION_VERSION or proof.get('runtime_version')!=VERSION or proof.get('contract_fingerprint')!=fingerprint(contract):raise ValueError('Native admission missing, stale or different original source/start')
    if not isinstance(proof.get('private_specification'),dict)or proof['private_specification'].get('kind')!=contract['reddit_native_task']['kind']:raise ValueError('Private validated task reference missing')
    cycles=proof.get('cycles')
    if proof.get('passed')is not True or not isinstance(cycles,list)or len(cycles)!=2:raise ValueError('Two fresh actual native cycles required')
    references=[];fingerprints=[]
    for cycle in cycles:
        row=cycle.get('task');refs=cycle.get('reference_sha256');fp=cycle.get('initial_fingerprint')
        if not isinstance(row,dict)or row.get('task_id')!=contract['task_id']or row.get('source_task_id')!=contract['source_task_id']or row.get('kind')!=contract['reddit_native_task']['kind']:raise ValueError('Native normal source binding mismatch')
        if any(cycle.get(k)is not True for k in('references_unchanged','protected_records_unchanged','all_sources_protected'))or cycle.get('protection_version')!='reddit-complete-protected-chunks-v3':raise ValueError('Native read-only protection failed')
        if not isinstance(refs,str)or not re.fullmatch('[0-9a-f]{64}',refs)or not isinstance(fp,str)or fp!=cycle.get('final_fingerprint'):raise ValueError('Incomplete native reference/reset proof')
        if any(row.get(k)is not True for k in('original_first_start_preserved','passed_controls','whole_native_state_unchanged','passed'))or row.get('protected_boundary_pending')is not False or row.get('actor_attempts')!=0 or row.get('api_calls')!=0:raise ValueError('Native controls incomplete or contain model/API attempts')
        controls=row.get('controls',{});wanted={'positive':'success','wrong_object':'failure','404':'failure','login':'failure','no_op':'success'if contract['reddit_native_task'].get('initial_may_already_satisfy')else'failure'}
        if answer_fields(contract):wanted['wrong_answer']='failure'
        if any(controls.get(k)!=v for k,v in wanted.items())or controls!=row.get('expected_controls'):raise ValueError('Strict native positive/negative/no-op controls missing')
        extra=row.get('extended_controls',{})
        required_extra={'profile_settings':('profile-only','settings-only'),'username_settings':('direct-settings-without-username',)}.get(contract['reddit_native_task']['kind'],())
        if any(extra.get(k)!='failure'for k in required_extra)or any(v!='failure'for k,v in extra.items()if k!='positive-partial'):raise ValueError('Native incomplete access control missing or passed')
        if contract['reddit_native_task']['kind']=='dated_comments'and controls.get('incomplete_collection')!='failure':raise ValueError('Dated comments require actual incomplete pagination rejection')
        if row.get('initial_fingerprint')!=fp or row.get('final_fingerprint')!=fp:raise ValueError('Source native baseline changed')
        references.append(refs);fingerprints.append(fp)
    if len(set(references))!=1 or len(set(fingerprints))!=1:raise ValueError('Fresh native snapshots differ')


def admission(contract,normal_result,normal_contract,normal_reference):
    if fingerprint(contract)!=fingerprint(normal_contract)or normal_contract.get('native_family')!=contract.get('reddit_native_task'):raise ValueError('Original normal contract parameters changed')
    if normal_result.get('version')!=NORMAL_VERSION or normal_result.get('status')!='completed'or any(normal_result.get(k)is not True for k in('references_equal','protected_records_unchanged'))or normal_result.get('api_calls')!=0 or normal_result.get('actor_attempts')!=0:raise ValueError('Completed two-fresh native controls required')
    if contract['source_task_id']not in normal_result.get('passed_sources',[]):raise ValueError('Source was not admitted by native controls')
    proof={'private_specification':specification(contract,normal_reference),'admission_version':ADMISSION_VERSION,'runtime_version':VERSION,'contract_fingerprint':fingerprint(contract),'passed':True,'cycles':[]}
    for old in normal_result.get('cycles',[]):
        rows=[r for r in old.get('records',[])if r.get('source_task_id')==contract['source_task_id']]
        row=_one(rows);new={k:old.get(k)for k in('cycle','references_unchanged','protected_records_unchanged','all_sources_protected','protection_version','reference_sha256','initial_fingerprint','final_fingerprint')};new['task']=copy.deepcopy(row);proof['cycles'].append(new)
    if hashlib.sha256(json.dumps(normal_reference,sort_keys=True).encode()).hexdigest()!=proof['cycles'][0]['reference_sha256']:raise ValueError('Private normal reference and completed proof differ')
    require_admission(contract,proof);return proof


def require_private_baseline(contract,reference,proof):
    require_admission(contract,proof)
    if specification(contract,reference)!=proof['private_specification']:raise ValueError('Native reset reference differs from independently controlled original task')


def feedback(judgment):
    return normal.public_feedback({'status':judgment['status'],'reward':judgment['reward'],'checks':judgment.get('checks',{})})
