"""Optional exact-field/tag forum creation for explicit training derivatives.

No prose-quality judge and no relaxed legacy name-only behavior. Native tag
UUIDs are private identities, never generated or inferred from tag labels.
"""
import hashlib
import json
import re
from uuid import UUID
from .reddit_submission import submission_state
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page

VERSION='reddit-exact-forum-v1'
ADMISSION_VERSION='reddit-exact-forum-admission-v1'


def validate_contract(c):
    s=c.get('exact_forum_creation')
    if(c.get('domain')!='reddit'or not isinstance(s,dict)or set(s)-{'name','title','description','sidebar','tags'}
       or not {'name','title','description','sidebar'}<=set(s)
       or any(not isinstance(s[k],str)or not s[k].strip()for k in('name','title','description','sidebar'))):raise ValueError('Exact native forum fields required')
    if 'tags'in s and(not isinstance(s['tags'],list)or not s['tags']or any(not isinstance(x,str)or not x.strip()for x in s['tags'])or len(set(s['tags']))!=len(s['tags'])):raise ValueError('Distinct exact native tags required')
    if(c.get('task_id')==c.get('source_task_id')or c.get('task_text_changed')is not True or c.get('original_evaluation_equivalence')is not False
       or c.get('heldout_quarantine')is not False or c.get('goal')!=c.get('derived_goal')or not isinstance(c.get('goal'),str)
       or not c['goal'].strip()or c['goal']==c.get('original_goal')):raise ValueError('Explicit revised training goal/source mapping required')


def fingerprint(c):
    validate_contract(c)
    keys=('task_id','source_task_id','domain','goal','derived_goal','original_goal','start_path','recorded_start_paths','source_trace_ids','exact_forum_creation','task_text_changed','original_evaluation_equivalence','heldout_quarantine','task_version')
    return hashlib.sha256(json.dumps({k:c.get(k)for k in keys},sort_keys=True).encode()).hexdigest()


def related_digest(site,forum_ids):
    if any(type(x)is not int or x<=0 for x in forum_ids)or len(set(forum_ids))!=len(forum_ids):raise ValueError('Exact original forum identities required')
    related=select_rows(site,"SELECT DISTINCT k.table_name,k.column_name FROM information_schema.table_constraints t JOIN information_schema.key_column_usage k ON k.constraint_name=t.constraint_name AND k.constraint_schema=t.constraint_schema JOIN information_schema.constraint_column_usage r ON r.constraint_name=t.constraint_name AND r.constraint_schema=t.constraint_schema WHERE t.constraint_type='FOREIGN KEY' AND k.table_schema='public' AND r.table_name='forums' AND r.column_name='id' ORDER BY k.table_name,k.column_name")
    for row in related:
        if any(not isinstance(v,str)or not re.fullmatch('[a-z][a-z0-9_]*',v)for v in(row['table_name'],row['column_name'])):raise ValueError('Unexpected native relation identifier')
    records=[]
    # Keep large native relation scans individually bounded by select_rows;
    # never sort or concatenate every full content row in memory.
    for row in related:
        table,column=row['table_name'],row['column_name'];condition='"'+column+'" IN ('+','.join(map(str,forum_ids))+')'if forum_ids else'false'
        limbs=["COALESCE(sum(('x'||substr(h,"+str(i)+",8))::bit(32)::bigint)::text,'0')"for i in(1,9,17,25)]
        query="SELECT '"+table+'.'+column+"' AS relation,count(*) AS count,md5("+"||':'||".join(limbs)+") AS digest FROM (SELECT md5(row_to_json(x)::text) AS h FROM "+table+' x WHERE '+condition+' OFFSET 0) full_rows'
        result=select_rows(site,query)
        if(len(result)!=1 or result[0].get('relation')!=table+'.'+column or type(result[0].get('count'))is not int or result[0]['count']<0
           or not isinstance(result[0].get('digest'),str)or not re.fullmatch('[0-9a-f]{32}',result[0]['digest'])):raise ValueError('Missing or malformed protected forum relation')
        records+=result
    return {r['relation']:{'count':r['count'],'digest':r['digest']}for r in records}



def state(site,username,baseline=None):
    forums=[r['row']for r in select_rows(site,'SELECT row_to_json(f) AS row FROM forums f ORDER BY id')]
    old_ids=[r['id']for r in(baseline['forums']if baseline else forums)]
    return {'forums':forums,'protected_relations':related_digest(site,old_ids),
            'tags':select_rows(site,'SELECT id,name,normalized_name,description FROM forum_tags ORDER BY id'),
            'associations':select_rows(site,'SELECT forum_id,tag_id FROM forums_tags ORDER BY forum_id,tag_id'),
            'submissions':submission_state(site,username,baseline['submissions']if baseline else None)}


def _uuid(value):
    if not isinstance(value,str)or str(UUID(value))!=value:raise ValueError('Exact native tag UUID required')
    return value


def validate_state(value):
    if not isinstance(value,dict)or any(not isinstance(value.get(k),list)for k in('forums','tags','associations'))or not isinstance(value.get('submissions'),dict):raise ValueError('Missing forum/tag state')
    protected=value.get('protected_relations')
    if(not isinstance(protected,dict)or not protected or any(not isinstance(k,str)or not re.fullmatch(r'[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*',k)or not isinstance(v,dict)or type(v.get('count'))is not int or v['count']<0 or not isinstance(v.get('digest'),str)or not re.fullmatch('[0-9a-f]{32}',v['digest'])for k,v in protected.items())):raise ValueError('Complete protected forum relations required')
    forum_ids=[];tag_ids=[];links=[]
    for row in value['forums']:
        if(not isinstance(row,dict)or type(row.get('id'))is not int or row['id']<=0 or any(not isinstance(row.get(k),str)for k in('name','title'))or any(row.get(k)is not None and not isinstance(row.get(k),str)for k in('description','sidebar'))):raise ValueError('Malformed native forum record')
        forum_ids.append(row['id'])
    for row in value['tags']:
        if not isinstance(row,dict)or any(not isinstance(row.get(k),str)for k in('name','normalized_name')):raise ValueError('Malformed native tag record')
        tag_ids.append(_uuid(row.get('id')))
    for row in value['associations']:
        if not isinstance(row,dict)or set(row)!={'forum_id','tag_id'}or type(row['forum_id'])is not int or row['forum_id']<=0:raise ValueError('Malformed tag association')
        links.append((row['forum_id'],_uuid(row['tag_id'])))
    if len(set(forum_ids))!=len(forum_ids)or len(set(tag_ids))!=len(tag_ids)or len(set(links))!=len(links):raise ValueError('Duplicate native identities')
    if any(f not in forum_ids or t not in tag_ids for f,t in links):raise ValueError('Orphan native tag association')


def validate_initial(c,value):
    validate_contract(c);validate_state(value)
    if any(r['name'].casefold()==c['exact_forum_creation']['name'].casefold()for r in value['forums']):raise ValueError('Declared new forum already exists')
    s=value['submissions']
    if type(s.get('user_id'))is not int or s['user_id']<=0 or s.get('added')!=[]:raise ValueError('Clean task account/submission baseline required')


def evaluate(c,page,initial,final,*,site_origin,runtime_error=None):
    validate_contract(c);unknown=lambda why:{'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':why}
    if runtime_error:return unknown('Environment or inference error')
    if not isinstance(page,dict)or type(page.get('http_status'))is not int or not 200<=page['http_status']<500:return unknown('Missing terminal page or server/transport error')
    try:validate_initial(c,initial);validate_state(final)
    except (ValueError,KeyError,TypeError):return unknown('Malformed native forum/tag baseline or final state')
    old={r['id']:r for r in initial['forums']};current={r['id']:r for r in final['forums']};added=[r for r in final['forums']if r['id']not in old]
    before=initial['submissions'];after=final['submissions'];spec=c['exact_forum_creation']
    if(before.get('user_id')!=after.get('user_id')or before.get('known_id_ranges')!=after.get('known_id_ranges')or not isinstance(after.get('protected_content'),dict)or not isinstance(after.get('added'),list)):return unknown('Mismatched native account/submission baseline')
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),'existing_forums_unchanged':all(current.get(k)==v for k,v in old.items()),
            'submission_baseline_unchanged':before.get('user_id')==after.get('user_id')and before.get('known_id_ranges')==after.get('known_id_ranges')and before.get('protected_content')==after.get('protected_content')and after.get('added')==[],
            'one_forum_saved':len(added)==1,'existing_forum_relations_unchanged':initial.get('protected_relations')==final.get('protected_relations')}
    old_tags={r['id']:r for r in initial['tags']};tags={r['id']:r for r in final['tags']};links={(r['forum_id'],r['tag_id'])for r in final['associations']};old_links={(r['forum_id'],r['tag_id'])for r in initial['associations']}
    checks['existing_tags_unchanged']=all(tags.get(k)==v for k,v in old_tags.items())
    checks['existing_tag_links_unchanged']=old_links<=links and all((f,t)in old_links for f,t in links if f in old)
    if len(added)==1:
        forum=added[0]
        for key in('name','title','description','sidebar'):checks['requested_'+key]=forum[key]==spec[key]
        own=[tags[t]for f,t in links if f==forum['id']]
        expected=spec.get('tags',[])
        checks['requested_native_tags']=sorted(r['name']for r in own)==sorted(expected)and len({r['normalized_name']for r in own})==len(own)
        checks['new_tags_belong_to_requested_forum']=all(t in {r['id']for r in own}for t in set(tags)-set(old_tags))
        checks['no_unrelated_new_tag_links']=all(f==forum['id']or(f,t)in old_links for f,t in links)
    else:checks['no_unrelated_tag_creation']=initial['tags']==final['tags']and initial['associations']==final['associations']
    passed=all(checks.values())
    return {'version':VERSION,'status':'success'if passed else'failure','reward':float(passed),'checks':checks,'reason':None}


def expected_controls(c):
    validate_contract(c)
    names=['no_op','filled_unsaved','wrong_name','wrong_title','wrong_description','wrong_sidebar','404','login']
    if'tags'in c['exact_forum_creation']:names+=['wrong_tags']
    return dict.fromkeys(names,'failure')|{'positive':'success','saved_then_home':'success'}


def require_admission(c,proof):
    validate_contract(c)
    if(proof.get('version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c)or proof.get('passed')is not True
       or proof.get('reset_mode')!='two_fresh_sites_restored_per_source'or proof.get('api_calls')!=0 or len(proof.get('cycles',[]))!=2):raise ValueError('Stale or incomplete exact-forum admission')
    cycles=proof['cycles']
    for row in cycles:
        validate_initial(c,row.get('initial_state'))
        if(row.get('passed')is not True or row.get('checks')!=expected_controls(c)or row.get('initial_valid')is not True or row.get('restored')is not True
           or row.get('initial_state')!=row.get('final_state')or not row.get('initial_fingerprint')or row['initial_fingerprint']!=row.get('final_fingerprint')
           or not row.get('private_protected_before')or row['private_protected_before']!=row.get('private_protected_after')):raise ValueError('Exact field/tag controls or full restoration incomplete')
    if cycles[0]['initial_state']!=cycles[1]['initial_state']or cycles[0]['initial_fingerprint']!=cycles[1]['initial_fingerprint']or cycles[0]['private_protected_before']!=cycles[1]['private_protected_before']:raise ValueError('Fresh exact-forum baselines differ')
