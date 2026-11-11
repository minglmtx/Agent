"""Native saved submissions. Private DB state is never an actor observation.

Only deterministic creation conditions are supported. No keyword approximation
for creative quality, image semantics, article relevance or question quality.
"""
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint
from urllib.parse import urlsplit

VERSION='reddit-submission-v1'
ADMISSION_VERSION='reddit-submission-admission-v1'
CONTENT_COLUMNS='id,forum_id,user_id,title,url,body,image_id,media_type,visibility'


def validate_contract(c):
    s=c['submission']
    if c.get('domain')!='reddit' or s.get('operation')!='create' or set(s)-{'operation','forum','title','url'}:
        raise ValueError('Unsupported submission condition')
    if s.get('forum') is not None and (not isinstance(s['forum'],str) or not s['forum']):
        raise ValueError('Invalid requested forum')
    for field in ('title','url'):
        if field in s and (not isinstance(s[field],str) or not s[field].strip()):
            raise ValueError('Requested submission field must be nonempty')
    if 'url' in s:
        canonical_url(s['url'])


def canonical_url(value):
    """Compare stored links without fetching their destination or ignoring paths."""
    if not isinstance(value,str) or value != value.strip() or any(ord(ch)<32 for ch in value):
        raise ValueError('Malformed submission URL')
    u=urlsplit(value)
    if u.scheme not in ('http','https') or not u.hostname or u.username is not None or u.password is not None:
        raise ValueError('An absolute HTTP(S) URL without credentials is required')
    port=u.port if u.port is not None else (443 if u.scheme=='https' else 80)
    return (u.scheme,u.hostname.lower(),port,u.path or '/',u.query,u.fragment)


def id_ranges(ids):
    """Native imported IDs are not ordered by creation time; new IDs may be low."""
    if any(type(i) is not int or i<=0 for i in ids) or ids!=sorted(set(ids)):
        raise ValueError('Malformed native ID baseline')
    ranges=[]
    for ident in ids:
        if ranges and ident==ranges[-1][1]+1:ranges[-1][1]=ident
        else:ranges.append([ident,ident])
    return ranges


def ranges_predicate(ranges):
    end=0;parts=[]
    for lo,hi in ranges:
        if type(lo) is not int or type(hi) is not int or not end<lo<=hi:
            raise ValueError('Invalid protected ID range')
        parts.append(f'id BETWEEN {lo} AND {hi}');end=hi
    return '('+' OR '.join(parts)+')' if parts else 'false'


def submission_state(site,username,baseline=None):
    from .reddit_submission_state_stream import submission_state as native_stream
    return native_stream(site,username,baseline)


def validate_initial(c,state):
    validate_contract(c)
    if not state or state.get('added')!=[] or type(state.get('user_id')) is not int:
        raise ValueError('Missing or dirty submission baseline')
    name=c['submission'].get('forum')
    if name and len([r for r in state['forums'] if r['name']==name])!=1:
        raise ValueError('Requested forum unavailable or ambiguous')


def fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','submission','heldout_quarantine','start_revision','goal_revision','initial_page_policy')})


def evaluate_submission(c,page,initial,final,*,site_origin,runtime_error=None):
    validate_contract(c)
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:
        return unknown('Missing terminal page or transport/server error')
    if not initial or not final or initial.get('user_id')!=final.get('user_id') or initial.get('known_id_ranges')!=final.get('known_id_ranges'):
        return unknown('Missing or mismatched submission baseline')
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
        'existing_content_unchanged':initial['protected_content']==final['protected_content'],
        'forums_unchanged':initial['forums']==final['forums'],
        'one_submission_saved':len(final['added'])==1}
    if len(final['added'])==1:
        row=final['added'][0];name=c['submission'].get('forum')
        forums={r['id']:r['name'] for r in initial['forums']}
        checks.update(correct_author=row['user_id']==initial['user_id'],
            requested_forum=row['forum_id'] in forums and (name is None or forums[row['forum_id']]==name),
            title_saved=isinstance(row['title'],str) and bool(row['title'].strip()),
            publicly_visible=row['visibility']=='visible')
        spec=c['submission']
        if 'title' in spec:
            checks['requested_title']=row['title']==spec['title']
        if 'url' in spec:
            try: matches=canonical_url(row.get('url'))==canonical_url(spec['url'])
            except ValueError: matches=False
            checks['requested_url']=matches and row.get('media_type')=='url'
    passed=all(checks.values())
    return {'version':VERSION,'status':'success' if passed else 'failure','reward':float(passed),'checks':checks,'reason':None}


def expected_controls(c):
    out=dict.fromkeys(['no_op','filled_unsaved','invalid_form','404','login'],'failure')
    if c['submission'].get('forum'):out['wrong_forum']='failure'
    for field in ('title','url'):
        if field in c['submission']:out['wrong_'+field]='failure'
    return out|{'positive':'success','saved_then_home':'success'}


def submission_feedback(j):
    meanings={'page_valid':'The final page is a valid page on the task website.',
        'existing_content_unchanged':'Previously existing submissions remain unchanged.',
        'forums_unchanged':'Existing forum identities remain unchanged.',
        'one_submission_saved':'One new submission has actually been saved.',
        'correct_author':'The submission belongs to the task account.',
        'requested_forum':'The submission is in a forum allowed by the task.',
        'title_saved':'The saved submission has a nonempty title.',
        'publicly_visible':'The saved submission is visible rather than removed.',
        'requested_title':'The saved title matches the title requested in the task.',
        'requested_url':'The saved link matches the URL requested in the task.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),
        'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in j['checks'].items()],
        'action_sequence_provided':False,'reference_values_provided':False}


def require_submission_admission(c,proof):
    validate_contract(c)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c):
        raise ValueError('Quarantined or stale submission admission')
    rows=proof.get('cycles',[])
    if not proof.get('passed') or len(rows)!=2:raise ValueError('Two independent controls/reset cycles required')
    for r in rows:
        validate_initial(c,r.get('initial_state'))
        if not r.get('passed') or not r.get('initial_valid') or r.get('checks')!=expected_controls(c):
            raise ValueError('Submission controls incomplete')
        if r.get('final_state')!=r['initial_state'] or not r.get('restored'):
            raise ValueError('Submission fixture cleanup incomplete')
        if not r.get('initial_fingerprint') or r['initial_fingerprint']!=r.get('final_fingerprint'):
            raise ValueError('Protected account state changed')
    if rows[0]['initial_state']!=rows[1]['initial_state'] or rows[0]['initial_fingerprint']!=rows[1]['initial_fingerprint']:
        raise ValueError('Submission reset baseline differs')
