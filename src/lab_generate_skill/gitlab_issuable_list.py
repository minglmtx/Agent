"""Issue/MR list identity, status and rendered objects, independent of actor claims."""
import re
from urllib.parse import urlsplit,parse_qs,unquote
from .site_database import select_rows
from .gitlab_directory import directory_access_reference


def list_reference(site,spec):
    kind=spec['kind']
    if kind not in ('issues','merge_requests'):raise ValueError('Unsupported issuable kind')
    access=directory_access_reference(site,spec['username']);user=access['user']
    project=None
    if spec.get('project_path'):
        path="'"+spec['project_path'].replace("'","''")+"'"
        matches=select_rows(site,"SELECT p.id,p.name,r.path FROM projects p JOIN routes r ON p.id=r.source_id AND r.source_type='Project' WHERE r.path="+path)
        if len(matches)!=1 or matches[0]['id'] not in access['project_ids']:raise ValueError('Project missing or inaccessible')
        project=matches[0]
    elif not spec.get('assigned_to_current_user'):raise ValueError('Global list must specify an account filter')
    table=kind;field='project_id' if kind=='issues' else 'target_project_id'
    where='x.'+field+' IN ('+','.join(map(str,access['project_ids']))+')'
    if project:where+=' AND x.'+field+'='+str(project['id'])
    if spec.get('assigned_to_current_user'):
        relation,key=('issue_assignees','issue_id') if kind=='issues' else ('merge_request_assignees','merge_request_id')
        where+=' AND EXISTS (SELECT 1 FROM '+relation+' a WHERE a.'+key+'=x.id AND a.user_id='+str(user['id'])+')'
    # Do not silently count hidden confidential issues. This adapter is admitted
    # only for snapshots whose scoped issue collection has no such ambiguity.
    if kind=='issues' and select_rows(site,'SELECT count(*) AS n FROM issues x WHERE '+where+' AND x.confidential=true')[0]['n']:
        raise ValueError('Confidential issue access needs a separate native permission adapter')
    rows=select_rows(site,'SELECT x.id,x.iid,x.title,x.state_id,r.path AS project_path FROM '+table+' x JOIN routes r ON r.source_id=x.'+field+" AND r.source_type='Project' WHERE "+where+' ORDER BY x.id')
    return {'user_id':user['id'],'username':user['username'],'project':project,'rows':rows}


def verify_list_reference(site,spec):
    if list_reference(site,spec)!=spec['reference']:raise RuntimeError('Issuable list differs from pinned account/object reference')


def read_issuable_list(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e.getClientRects().length;
      const tabs=[...document.querySelectorAll('a.nav-link')].filter(visible).map(e=>({
        text:e.innerText.trim().replace(/\s+/g,' '),active:e.classList.contains('active')}))
        .filter(e=>/^(Open|Closed|Merged|All)(?:\s+[\d,]+)?$/.test(e.text));
      const links=[...document.querySelectorAll('a[data-qa-selector="issuable_title_link"],a.js-prefetch-document')]
        .filter(e=>visible(e)&&/\/-\/(issues|merge_requests)\/\d+$/.test(new URL(e.href,location.href).pathname)&&e.innerText.trim());
      const body=document.body.innerText;
      return {user_id:window.gon?.current_user_id,tabs,
        project_ids:[...new Set([...document.querySelectorAll('[data-project-id]')].map(e=>e.getAttribute('data-project-id')))],
        items:links.map(e=>({path:new URL(e.href,location.href).pathname,title:e.innerText.trim().replace(/\s+/g,' ')})),
        issue_onboarding:body.includes('Use issues to collaborate on ideas, solve problems, and plan work'),
        merge_request_onboarding:body.includes("Merge requests are a place to propose changes you've made to a project and discuss those changes with others"),
        no_results:/There are no (?:open |closed |merged )?(?:issues|merge requests)|No (?:issues|merge requests) (?:found|to show)/i.test(body),
        needs_filter:body.includes('Please select at least one filter to see results')};
    }''')


def list_checks(spec,state,url):
    if not isinstance(state,dict) or any(not isinstance(state.get(k),list) for k in ('tabs','items')):raise ValueError('Missing native issue/MR list capture')
    kind=spec['kind'];requested=spec['state'];ref=spec['reference'];path=urlsplit(url).path.rstrip('/')
    if requested not in ('opened','closed','merged','all') or (kind=='issues' and requested=='merged'):raise ValueError('Unsupported list status')
    target='/'+spec['project_path']+'/-/'+kind if spec.get('project_path') else '/dashboard/'+kind
    query=parse_qs(urlsplit(url).query,keep_blank_values=True)
    unambiguous=all(len(set(v))==1 for v in query.values())
    q={k:v[0] for k,v in query.items()}
    params={'state','scope','sort','page'}|({'assignee_username'} if spec.get('assigned_to_current_user') else set())
    scope=path==target and state.get('user_id')==ref['user_id'] and not any(v for k,v in q.items() if k not in params) and q.get('scope','all')=='all'
    if spec.get('assigned_to_current_user'):scope &= q.get('assignee_username')==spec['username']
    page=q.get('page','1');page_ok=page.isdecimal() and int(page)>0
    checks={'issuable_parameters_unambiguous':unambiguous,'issuable_collection_scope':scope,
      'issuable_status_filter':q.get('state','opened')==requested,'issuable_results_loaded':not state.get('needs_filter')}
    status={'opened':1,'closed':2,'merged':3}.get(requested)
    pool=[r for r in ref['rows'] if requested=='all' or r['state_id']==status]
    if spec.get('project_path') and not ref['rows']:
        # Empty projects have neither item paths nor tab counters. Retain the
        # server-rendered project identity so a different empty project cannot
        # pass by changing only the browser address and document title.
        if not isinstance(state.get('project_ids'),list):raise ValueError('Empty project identity capture missing')
        checks['issuable_empty_project_identity']=state['project_ids']==[str(ref['project']['id'])]
    page_ok &= int(page) <= max(1,(len(pool)+19)//20) if page_ok else False
    label={'opened':'Open','closed':'Closed','merged':'Merged','all':'All'}[requested]
    active=[r['text'] for r in state['tabs'] if r['active']]
    native_onboarding=state.get('issue_onboarding' if kind=='issues' else 'merge_request_onboarding') is True
    # GitLab omits status tabs for a project with no records at all. The same
    # MR introduction also appears below Open 0 when merged records exist;
    # that case must still pass the normal tab and independent count checks.
    onboarding=bool(spec.get('project_path')) and not ref['rows'] and native_onboarding and not state['tabs']
    if onboarding:
        checks['issuable_active_tab']=requested=='opened' and not active
        checks['issuable_result_count']=not state['items']
    else:
        checks['issuable_active_tab']=len(active)==1 and re.fullmatch(re.escape(label)+r'\s+[\d,]+',active[0]) is not None
        count=int(re.sub(r'\D','',active[0])) if checks['issuable_active_tab'] else None
        checks['issuable_result_count']=count==len(pool)
    paths=[r['path'] for r in state['items']]
    expected={'/'+r['project_path']+'/-/'+kind+'/'+str(r['iid']):' '.join(r['title'].split()) for r in pool}
    visible_count=min(20,max(0,len(pool)-(int(page)-1)*20)) if page_ok else -1
    checks['issuable_rendered_objects']=len(paths)==len(set(paths))==visible_count and all(p in expected and row['title']==expected[p] for p,row in zip(paths,state['items']))
    if len(pool)<=20:checks['issuable_rendered_objects'] &= set(paths)==set(expected)
    if not pool and not onboarding:
        checks['issuable_empty_visible']=state.get('no_results') is True or (kind=='merge_requests' and native_onboarding)
    return checks


FEEDBACK={
 'issuable_parameters_unambiguous':'The applied issue or merge-request parameters are unambiguous.',
 'issuable_collection_scope':'The list belongs to the requested project or account and preserves the requested scope.',
 'issuable_status_filter':'The requested open, closed, merged or all-status selection is applied.',
 'issuable_results_loaded':'The native result list has loaded and is not asking for a missing filter.',
 'issuable_active_tab':'The displayed list tab matches the requested status.',
 'issuable_result_count':'The displayed total matches the requested collection.',
 'issuable_empty_project_identity':'The empty list belongs to the requested project.',
 'issuable_rendered_objects':'The rendered entries have the correct object identities, titles and status.',
 'issuable_empty_visible':'The empty result is explicitly displayed.'}
