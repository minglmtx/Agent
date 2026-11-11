"""Account-scoped native to-do lists and persisted state, independent of actor claims."""
from urllib.parse import urlsplit, parse_qs
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION='gitlab-todo-v1'
ADMISSION_VERSION='gitlab-todo-admission-v1'


def display_text(value):
    """HTML renders consecutive whitespace as one space; retain word/case content."""
    return ' '.join(value.split())


def todo_state(site,username):
    name="'"+username.replace("'","''")+"'"
    users=select_rows(site,'SELECT id,username FROM users WHERE username='+name)
    if len(users)!=1:raise ValueError('Missing or ambiguous to-do account')
    user=users[0]
    rows=select_rows(site,"SELECT t.id,t.user_id,t.project_id,t.target_type,t.target_id,t.state,t.author_id,t.action,t.created_at, "
        "p.namespace_id,r.path AS project_path,n.name AS namespace_name,u.name AS author_name, "
        "CASE WHEN t.target_type='Issue' THEN i.title ELSE m.title END AS title, "
        "CASE WHEN t.target_type='Issue' THEN i.iid ELSE m.iid END AS iid "
        "FROM todos t JOIN projects p ON p.id=t.project_id JOIN namespaces n ON n.id=p.namespace_id "
        "JOIN routes r ON r.source_id=p.id AND r.source_type='Project' JOIN users u ON u.id=t.author_id "
        "LEFT JOIN issues i ON t.target_type='Issue' AND i.id=t.target_id "
        "LEFT JOIN merge_requests m ON t.target_type='MergeRequest' AND m.id=t.target_id "
        "WHERE t.user_id="+str(int(user['id']))+" ORDER BY t.id")
    if any(r['title'] is None or r['iid'] is None for r in rows):raise ValueError('Unsupported or missing to-do target')
    return {'user':user,'items':rows}


def read_todo_page(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e.getClientRects().length;
      const items=[...document.querySelectorAll('li.todo')].filter(visible);
      return {present:!!document.querySelector('.js-todos-pending'),user_id:window.gon?.current_user_id,
        active_tabs:[...document.querySelectorAll('a.js-todos-pending.active,a.js-todos-done.active')].filter(visible).map(e=>e.classList.contains('js-todos-pending')?'pending':'done'),
        buttons:[...document.querySelectorAll('button')].filter(visible).map(e=>e.innerText.trim()),
        empty:document.body.innerText.includes('Nothing is on your to-do list.'),
        items:items.map(e=>({id:Number(e.id.replace('todo_','')),path:e.querySelector('a.todo-target-link')?.getAttribute('href'),
          title:e.querySelector('.todo-target-title')?.innerText.trim().replace(/\s*·\s*$/,''),
          state:e.classList.contains('todo-pending')?'pending':e.classList.contains('todo-done')?'done':null}))};
    }''')


def validate_initial(c,state):
    s=c['todo'];op=s.get('operation')
    if c['domain']!='gitlab' or op not in ('view','mark_done','restore','mark_all_done'):raise ValueError('Unsupported to-do operation')
    if not isinstance(state,dict) or not state.get('user') or not isinstance(state.get('items'),list):raise ValueError('Missing to-do baseline')
    if op in ('mark_done','restore'):
        matches=[r for r in state['items'] if display_text(r['title'])==display_text(s['title']) and r['project_path']==s['project_path'] and r['state']==('pending' if op=='mark_done' else 'done')]
        if len(matches)!=1:raise ValueError('Requested to-do missing, ambiguous, or already completed')
    if op=='mark_all_done' and not any(r['state']=='pending' for r in state['items']):raise ValueError('No pending to-dos')
    if op=='view':
        if set(s)-{'operation','filters','sort','state'}:raise ValueError('Unknown to-do view condition')
        if set(s.get('filters',{}))-{'type','action','author_name','namespace_name','project_path'}:raise ValueError('Unsupported to-do filter')
        if s.get('state','pending') not in ('pending','done'):raise ValueError('Unsupported to-do state')
        if s.get('sort') not in (None,'created_asc','created_desc'):raise ValueError('Unsupported to-do sort')


def filter_values(s,initial):
    values={}
    for key,value in s.get('filters',{}).items():
        if key in ('type','action'):
            # Native TodosFinder uses numeric action_id; `action` accepts the
            # symbolic enum name, not the database integer.
            values['action_id' if key=='action' else key]=str(value);continue
        field,param={'author_name':('author_id','author_id'),'namespace_name':('namespace_id','group_id'),'project_path':('project_id','project_id')}[key]
        ids={r[field] for r in initial['items'] if r[key]==value}
        if len(ids)!=1:raise ValueError('Missing or ambiguous to-do filter identity')
        values[param]=str(next(iter(ids)))
    return values


def requested_ids(c,initial):
    s=c['todo'];op=s['operation']
    if op=='mark_all_done':return {r['id'] for r in initial['items'] if r['state']=='pending'}
    if op in ('mark_done','restore'):return {r['id'] for r in initial['items'] if display_text(r['title'])==display_text(s['title']) and r['project_path']==s['project_path'] and r['state']==('pending' if op=='mark_done' else 'done')}
    return set()


def evaluate_todo(c,page,initial,final,*,site_origin,runtime_error=None):
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    try:validate_initial(c,initial)
    except (ValueError,KeyError,TypeError) as exc:return unknown(str(exc))
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:return unknown('Missing page or transport/server error')
    if not final or final.get('user')!=initial['user'] or not isinstance(final.get('items'),list):return unknown('Missing or changed to-do account state')
    s=c['todo'];op=s['operation'];checks={'page_valid':valid_initial_page(page,site_origin=site_origin)}
    before={r['id']:r for r in initial['items']};after={r['id']:r for r in final['items']}
    if op!='view':
        targets=requested_ids(c,initial);state='pending' if op=='restore' else 'done'
        checks['requested_todos_saved']=bool(targets) and all(after.get(i,{}).get('state')==state for i in targets)
        # Check the target state separately; the remaining metadata and all
        # non-target state must be unchanged even when the target is not done.
        expected={i:{**r,**({'state':after.get(i,{}).get('state')} if i in targets else {})} for i,r in before.items()}
        checks['other_todo_fields_unchanged']=after==expected
    else:
        checks['todo_records_unchanged']=initial==final
        view=page.get('todo')
        if not isinstance(view,dict) or type(view.get('present')) is not bool:return unknown('Missing native to-do capture')
        checks['todo_list_present']=view['present']
        if view['present']:
            if any(not isinstance(view.get(k),list) for k in ('items','buttons','active_tabs')):return unknown('Malformed native to-do capture')
            q=parse_qs(urlsplit(page['url']).query,keep_blank_values=True)
            checks['todo_parameters_unambiguous']=all(len(set(v))==1 for v in q.values())
            q={k:v[0] for k,v in q.items()}
            state=s.get('state','pending');params=filter_values(s,initial)
            checks['requested_todo_filters']=all(q.get(k)==v for k,v in params.items())
            checks['todo_collection_scope']=urlsplit(page['url']).path.rstrip('/')=='/dashboard/todos' and view['user_id']==initial['user']['id'] and q.get('state','pending')==state and view['active_tabs']==[state] and not any(v for k,v in q.items() if k not in set(params)|{'state','sort','page'}) and q.get('page','1')=='1'
            pool=[r for r in initial['items'] if r['state']==state]
            for key,value in s.get('filters',{}).items():pool=[r for r in pool if r['target_type' if key=='type' else key]==value]
            ids=[r['id'] for r in view['items']]
            checks['matching_todo_results']=len(ids)==len(set(ids)) and set(ids)=={r['id'] for r in pool}
            checks['rendered_todo_identities']=all(r['id'] in before and display_text(r['title'])==display_text(before[r['id']]['title']) and r['state']==before[r['id']]['state'] and r['path']=='/'+before[r['id']]['project_path']+'/-/'+('issues' if before[r['id']]['target_type']=='Issue' else 'merge_requests')+'/'+str(before[r['id']]['iid']) for r in view['items'])
            if not pool:checks['empty_todo_results_visible']=view.get('empty') is True
            if s.get('sort'):
                label={'created_asc':'Oldest created','created_desc':'Last created'}[s['sort']]
                checks['requested_todo_sort']=q.get('sort')==s['sort'] and label in view['buttons']
                checks['todo_values_in_order']=all(i in before for i in ids) and [before[i]['created_at'] for i in ids]==sorted([r['created_at'] for r in pool],reverse=s['sort']=='created_desc')
    ok=all(checks.values());return {'version':VERSION,'status':'success' if ok else 'failure','reward':float(ok),'checks':checks,'reason':None}


def expected_controls(c):
    names=['no_op','wrong_object','404','login']
    positive=['positive']
    if c['todo']['operation']=='view':names.append('url_only')
    else:names.append('unapplied_ui');positive.append('saved_then_home')
    return dict.fromkeys(names,'failure')|dict.fromkeys(positive,'success')


def todo_feedback(j):
    meanings={'page_valid':'The final page is valid on the task website.','requested_todos_saved':'The requested to-do state has actually been saved.',
      'other_todo_fields_unchanged':'Unrequested to-do records and fields remain unchanged.','todo_records_unchanged':'Viewing the list did not modify the stored to-dos.',
      'todo_list_present':'The native to-do list is displayed.','todo_parameters_unambiguous':'Applied list parameters are unambiguous.',
      'requested_todo_filters':'The requested to-do filters are applied.','todo_collection_scope':'The requested account and to-do collection are displayed.',
      'matching_todo_results':'The rendered result set matches the requested criteria.','rendered_todo_identities':'Displayed to-dos identify the actual stored targets.',
      'empty_todo_results_visible':'An empty result set is explicitly displayed.','requested_todo_sort':'The requested sorting is active.',
      'todo_values_in_order':'The actual to-do values follow the requested ordering.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in j['checks'].items()],'action_sequence_provided':False}


def contract_fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','todo','heldout_quarantine','start_revision','goal_revision')})


def require_todo_admission(c,proof):
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=contract_fingerprint(c):raise ValueError('Quarantined or stale to-do admission')
    rows=proof.get('cycles',[])
    if not proof.get('passed') or len(rows)!=2:raise ValueError('Two independent to-do/reset cycles required')
    for r in rows:
        validate_initial(c,r.get('initial_state'))
        if not r.get('passed') or not r.get('initial_valid') or r.get('checks')!=expected_controls(c):raise ValueError('To-do control failed')
        if not r.get('restored') or r.get('final_state')!=r['initial_state']:raise ValueError('To-do fixture cleanup not verified')
        if not r.get('initial_fingerprint') or r['initial_fingerprint']!=r.get('final_fingerprint'):raise ValueError('Protected project state changed')
    if rows[0]['initial_state']!=rows[1]['initial_state'] or rows[0]['initial_fingerprint']!=rows[1]['initial_fingerprint']:raise ValueError('To-do reset baseline differs')
