"""Bound native search/pipeline metadata; final scoring only, no actor strategy."""
import re
from urllib.parse import urlsplit,parse_qs,unquote

READ=r'''() => {
 const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const main=document.querySelector('main.content,#content-body')||document.querySelector('main');
 const links=[...document.querySelectorAll('a[href]')].filter(visible);
 return {url:location.href,account_id:window.gon?.current_user_id??null,body_page:document.body.dataset.page,
 active_search_scopes:links.filter(e=>e.classList.contains('active')&&new URL(e.href).pathname==='/search').map(e=>({url:e.href,label:e.innerText.trim()})),
 result_links:links.filter(e=>e.closest('.search-results,.search-result-row,.search-result,.js-search-results')).map(e=>({url:e.href,label:e.innerText.trim()})),
 pipeline_statuses:[...document.querySelectorAll('.ci-status-icon,.ci-status,[data-testid="ci-icon"],[data-testid="pipeline-status-icon"]')].filter(visible).map(e=>({text:e.innerText.trim(),label:e.getAttribute('aria-label'),title:e.getAttribute('title')||e.getAttribute('data-original-title'),parent_title:e.parentElement?.getAttribute('title'),parent_label:e.parentElement?.getAttribute('aria-label'),href:e.closest('a[href]')?.href})),
 pipeline_links:links.filter(e=>/\/-\/pipelines\/\d+$/.test(new URL(e.href).pathname)).map(e=>({url:e.href,label:e.innerText.trim(),title:e.getAttribute('title'),aria:e.getAttribute('aria-label')})),
 next_links:links.filter(e=>e.closest('.pagination')&&/^Next\s*$/i.test(e.innerText)).map(e=>e.href),
 main_text:main?.innerText||'',capture_truncated:false};}'''


def read(page):
    return page.evaluate(READ)


def active_scope(state, *, kind, term, project_id=None):
    rows=state.get('active_search_scopes')
    if not isinstance(rows,list)or len(rows)!=1:
        return False
    urls=[urlsplit(state.get('url','')),urlsplit(rows[0].get('url',''))]
    expected={'scope':[kind],'search':[term]}
    if project_id is not None:expected['project_id']=[str(project_id)]
    for url in urls:
        query=parse_qs(url.query,keep_blank_values=True)
        if (url.path!='/search' or any(query.get(k)!=v for k,v in expected.items())
                or set(query)-set(expected)-{'page'} or url.fragment):
            return False
    return True


def navigation_checks(spec,state,private,observations,*,control_mode=False):
    native=state.get('extended')
    if not isinstance(native,dict)or native.get('url')!=state.get('url'):
        raise ValueError('Coherent native search capture unavailable')
    code=spec['kind']=='repository_code_search'
    out={'exact_active_native_search':active_scope(native,kind='blobs' if code else 'merge_requests',term=spec['term'],project_id=private['project']['id']if code else None)}
    out['native_search_results_loaded']=native.get('body_page')=='search:show' and native.get('capture_truncated')is False and bool(native.get('main_text'))
    if code:
        paths=set();prefix='/'+private['project']['path']+'/-/blob/'
        for link in native.get('result_links',[]):
            path=unquote(urlsplit(link.get('url','')).path)
            if path.startswith(prefix):
                # The exact pinned branch is confirmed by the immutable Git
                # scope and actual native content. Never compare temporary bid.
                pieces=path[len(prefix):].split('/',1)
                if len(pieces)==2:paths.add(pieces[1])
        out['native_literal_code_result']=bool(paths) and paths<=set(private['git_match_paths'])
    if spec['kind']=='search_scope_transition':
        initial=next((r.get('native',{}).get('extended') for r in observations if r.get('event')=='issued_observation'),None)
        out['initial_issues_query_preserved']=bool(isinstance(initial,dict) and active_scope(initial,kind='issues',term=spec['term']))
    return out


def qualify_pipeline(spec,private,public):
    native=public.get('extended')
    expected=private['values']['pipeline_status'];pr=private['project'];mr=private['merge_request']
    target='/'+pr['path']+'/-/merge_requests/'+str(mr['iid'])+'/pipelines'
    if (not isinstance(native,dict)or unquote(urlsplit(native.get('url','')).path)!=target
            or native.get('account_id')!=private['account_id']or native.get('capture_truncated')is not False):
        raise ValueError('Bound requested native merge-request pipeline page unavailable')
    expected_ids={r['id']for r in private['pipelines']};public_ids=set()
    for link in native.get('pipeline_links',[]):
        match=re.fullmatch(re.escape('/'+pr['path']+'/-/pipelines/')+r'(\d+)',unquote(urlsplit(link.get('url','')).path))
        if match:public_ids.add(int(match[1]))
    if public_ids!=expected_ids:
        raise ValueError('Complete native MR pipeline association differs')
    latest=private['pipelines'][0]['id'];target_pipeline='/'+pr['path']+'/-/pipelines/'+str(latest)
    seen=set()
    for row in [*native.get('pipeline_statuses',[]),*native.get('pipeline_links',[])]:
        href=row.get('href')or row.get('url')
        if not href or unquote(urlsplit(href).path)!=target_pipeline:continue
        for key in ('text','label','title','parent_title','parent_label','aria'):
            text=row.get(key)
            if isinstance(text,str):
                for status in ('created','waiting_for_resource','preparing','pending','running','success','failed','canceled','skipped','manual','scheduled'):
                    if re.search(r'\b'+re.escape(status.replace('_',' '))+r'\b',text,re.I):seen.add(status)
    if seen!={expected}:
        raise ValueError('Public latest pipeline status absent or disagrees')
    return True
