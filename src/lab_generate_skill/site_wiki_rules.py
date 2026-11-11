"""Persisted native wiki creation, with explicit parameters or nonempty/format rules."""
import re
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION='site-wiki-v1'
ADMISSION_VERSION='site-wiki-admission-v1'


def normalize_path(path):
    # Native Postmill WikiPage::normalizePath, not a guessed URL transformation.
    return path.lower().replace('-','_')


def wiki_state(site,username):
    quoted="'"+username.replace("'","''")+"'"
    users=select_rows(site,'SELECT id FROM users WHERE username='+quoted)
    if len(users)!=1:raise ValueError('Missing or ambiguous wiki account')
    rows=select_rows(site,"SELECT p.id,p.path,p.normalized_path,p.locked,r.title,r.body,r.user_id AS author_id, "
        "(SELECT count(*) FROM wiki_revisions v WHERE v.page_id=p.id) AS revision_count, "
        "(SELECT count(*) FROM wiki_revisions v WHERE v.page_id=p.id AND v.timestamp=r.timestamp) AS latest_ties "
        "FROM wiki_pages p LEFT JOIN LATERAL (SELECT title,body,user_id,timestamp FROM wiki_revisions v "
        "WHERE v.page_id=p.id ORDER BY timestamp DESC LIMIT 1) r ON true ORDER BY p.id")
    for r in rows:
        if r['title'] is None or r['body'] is None or int(r['latest_ties'])!=1:raise ValueError('Missing or ambiguous native latest wiki revision')
        for k in ('id','author_id','revision_count','latest_ties'):r[k]=int(r[k])
    return {'user_id':int(users[0]['id']),'pages':rows}


def validate_contract(c):
    s=c['wiki']
    if c['domain']!='reddit' or s.get('operation')!='create':raise ValueError('Unsupported wiki operation')
    if s.get('path') is not None and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*(/[A-Za-z][A-Za-z0-9_-]*)*',s['path']):
        raise ValueError('Invalid native wiki resource path')
    if set(s)-{'operation','path','title','body','required_features','initial_empty'}:raise ValueError('Unknown wiki completion condition')
    for k in ('title','body'):
        if s.get(k) is not None and (not isinstance(s[k],str) or not s[k].strip()):raise ValueError('Empty exact wiki field')
    if not set(s.get('required_features',[]))<={'heading','bullet_list','html_code'}:raise ValueError('Unsupported deterministic wiki format condition')


def contract_fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','wiki','heldout_quarantine','start_revision','goal_revision','initial_page_policy')})


def validate_initial(c,state):
    validate_contract(c)
    if not isinstance(state,dict) or type(state.get('user_id')) is not int or not isinstance(state.get('pages'),list):raise ValueError('Missing wiki baseline')
    if c['wiki'].get('initial_empty') and state['pages']:raise ValueError('First-page creation requires an empty wiki')
    path=c['wiki'].get('path')
    if path and any(r['normalized_path']==normalize_path(path) for r in state['pages']):raise ValueError('Requested wiki page already exists')


def body_features(body):
    from markdown_it import MarkdownIt
    tokens=MarkdownIt('commonmark').parse(body)
    result={'heading':any(t.type=='heading_open' for t in tokens),
            'bullet_list':any(t.type=='bullet_list_open' for t in tokens),'html_code':False}
    for t in tokens:
        if t.type in ('fence','code_block') and re.search(r'<[A-Za-z][^>]*>',t.content):
            result['html_code']=True
    return result


def evaluate_wiki(c,page,initial,final,*,site_origin,runtime_error=None):
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    validate_contract(c)
    if runtime_error:return unknown('Environment or inference error')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:return unknown('Missing terminal page or transport/server error')
    if not initial or not final or initial.get('user_id')!=final.get('user_id'):return unknown('Missing or changed wiki account state')
    before={r['id']:r for r in initial['pages']};after={r['id']:r for r in final['pages']}
    added=[r for ident,r in after.items() if ident not in before];s=c['wiki']
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
            'existing_pages_unchanged':all(after.get(ident)==r for ident,r in before.items()),
            'one_new_page_saved':len(added)==1}
    if len(added)==1:
        r=added[0]
        checks['correct_author']=r['author_id']==initial['user_id']
        checks['requested_path']=s.get('path') is None or r['normalized_path']==normalize_path(s['path'])
        checks['title_saved']=bool(r['title'].strip()) and (s.get('title') is None or r['title']==s['title'])
        checks['body_saved']=bool(r['body'].strip()) and (s.get('body') is None or r['body'].replace('\r\n','\n')==s['body'].replace('\r\n','\n'))
        if s.get('required_features'):
            features=body_features(r['body'])
            for feature in s['required_features']:checks['format_'+feature]=features[feature]
    ok=all(checks.values())
    return {'version':VERSION,'status':'success' if ok else 'failure','reward':float(ok),'checks':checks,'reason':None}


def expected_controls(c):
    names=['no_op','filled_unsaved','invalid_form','404','login']
    if c['wiki'].get('path'):names.append('wrong_object')
    if c['wiki'].get('title') or c['wiki'].get('body') or c['wiki'].get('required_features'):names.append('wrong_content')
    return dict.fromkeys(names,'failure') | {'positive':'success','saved_then_home':'success'}


def wiki_feedback(j):
    meanings={'page_valid':'The final page is a valid page on the task website.',
              'existing_pages_unchanged':'Previously existing wiki pages remain unchanged.',
              'one_new_page_saved':'One new wiki page has actually been saved.',
              'correct_author':'The new page was saved by the task account.',
              'requested_path':'The saved page has the requested wiki resource path.',
              'title_saved':'The saved title satisfies the task requirement.',
              'body_saved':'The saved body satisfies the task requirement.',
              'format_heading':'The saved body contains a Markdown heading.',
              'format_bullet_list':'The saved body contains a Markdown bullet list.',
              'format_html_code':'The saved body contains a code example with HTML markup.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),
            'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in j['checks'].items()], 'action_sequence_provided':False}


def require_wiki_admission(c,proof):
    validate_contract(c)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=contract_fingerprint(c):raise ValueError('Quarantined or stale wiki admission')
    rows=proof.get('cycles',[])
    if not proof.get('passed') or len(rows)!=2:raise ValueError('Two independent wiki/reset cycles required')
    for r in rows:
        validate_initial(c,r.get('initial_state'))
        if not r.get('passed') or not r.get('initial_valid') or r.get('checks')!=expected_controls(c):raise ValueError('Wiki control failed')
        if not r.get('restored') or r.get('final_state')!=r['initial_state']:raise ValueError('Wiki fixture cleanup not verified')
        if not r.get('initial_fingerprint') or r['initial_fingerprint']!=r.get('final_fingerprint'):raise ValueError('Protected account state changed')
    if rows[0]['initial_state']!=rows[1]['initial_state'] or rows[0]['initial_fingerprint']!=rows[1]['initial_fingerprint']:raise ValueError('Wiki reset baseline differs')
