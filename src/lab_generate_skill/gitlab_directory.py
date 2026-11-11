"""Rendered GitLab project directory + independent pinned database references."""
from urllib.parse import urlsplit,parse_qs,unquote
from .site_database import select_rows
from .public_counts import parse_public_count

FIELDS=('id','path','name','description','visibility_level','star_count','archived','updated_at','last_activity_at')


def project_reference(site):
    return select_rows(site,"SELECT p.id,r.path,p.name,p.description,p.visibility_level,p.star_count,p.archived,p.updated_at,p.last_activity_at FROM projects p JOIN routes r ON p.id=r.source_id AND r.source_type='Project' ORDER BY p.id")


def directory_access_reference(site,username):
    # Mirror ProjectsFinder / Project.public_or_visible_to_user in the pinned
    # native image. Do not infer access from the actor's chosen result page.
    name="'"+username.replace("'","''")+"'"
    users=select_rows(site,"SELECT id,username,admin,external,state FROM users WHERE username="+name)
    if len(users)!=1 or users[0]['state']!='active' or users[0]['admin']:
        raise ValueError('Directory reference requires an active ordinary benchmark user')
    user=users[0]
    projects=select_rows(site,"SELECT p.id FROM projects p WHERE p.pending_delete=false AND p.marked_for_deletion_at IS NULL AND (p.visibility_level=20 OR (p.visibility_level=10 AND "+('false' if user['external'] else 'true')+") OR EXISTS (SELECT 1 FROM project_authorizations a WHERE a.project_id=p.id AND a.user_id="+str(int(user['id']))+")) ORDER BY p.id")
    authorized=select_rows(site,"SELECT p.id FROM projects p WHERE p.pending_delete=false AND p.marked_for_deletion_at IS NULL AND EXISTS (SELECT 1 FROM project_authorizations a WHERE a.project_id=p.id AND a.user_id="+str(int(user['id']))+") ORDER BY p.id")
    return {'user':user,'project_ids':[r['id'] for r in projects],
            'authorized_project_ids':[r['id'] for r in authorized]}


def verify_directory_reference(site,spec):
    if project_reference(site)!=spec['reference']:
        raise RuntimeError('Project directory differs from pinned database reference')
    access=spec.get('access_reference')
    if access is not None and directory_access_reference(site,access['user']['username'])!=access:
        raise RuntimeError('Project access differs from pinned benchmark account reference')
    if spec['kind']=='trending':
        rows=select_rows(site,'SELECT project_id FROM trending_projects ORDER BY project_id')
        if [r['project_id'] for r in rows]!=spec['trending_project_ids']:
            raise RuntimeError('Trending projects differ from pinned native reference')


def read_directory_page(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e.getClientRects().length;
      const q=document.querySelector('input[name="name"][type="search"]');
      const texts=selector=>[...document.querySelectorAll(selector)].filter(visible).map(e=>e.innerText.trim());
      return {present:!!q,query:q?q.value:null,
       sort_labels:texts('a.is-active').filter(x=>['Name','Most stars','Updated date','Created date'].includes(x)),
       button_labels:texts('button'),
       tabs:[...document.querySelectorAll('a.nav-link.active')].filter(visible).map(e=>({text:e.innerText.trim(),path:e.getAttribute('href')})),
       items:[...document.querySelectorAll('.project-row')].map(e=>({
         path:e.querySelector('a.project')?.getAttribute('href'),
         stars:e.querySelector('a.stars')?.innerText.trim(),
         visibility:[...e.querySelectorAll('[title],[data-original-title]')].map(x=>x.getAttribute('data-original-title')||x.title).find(x=>/^(Public|Private|Internal) - /.test(x))
       }))};
    }''')


def directory_checks(spec,state,url):
    if not isinstance(state,dict) or type(state.get('present')) is not bool:
        raise ValueError('Missing project directory capture')
    checks={'project_directory_present':state['present']}
    if not state['present']:return checks
    if not all(isinstance(state.get(k),list) for k in ('sort_labels','button_labels','tabs','items')) or not isinstance(state.get('query'),str):
        raise ValueError('Malformed project directory capture')
    query=parse_qs(urlsplit(url).query,keep_blank_values=True)
    # GitLab's native AJAX name filter repeats e.g. sort=name_asc. Identical
    # repetitions are unambiguous; conflicting scalar values remain rejected.
    if any(len(set(values))!=1 for values in query.values()):return {**checks,'directory_parameters_unambiguous':False}
    query={k:[v[0]] for k,v in query.items()}
    reference=spec['reference'];kind=spec['kind']
    if not reference or any(not all(k in r for k in FIELDS) for r in reference):raise ValueError('Missing project reference fields')
    refs={r['path']:r for r in reference};items=state['items'];paths=[];stars=[]
    for item in items:
        if not isinstance(item.get('path'),str) or not isinstance(item.get('stars'),str):raise ValueError('Incomplete rendered project identity or star count')
        paths.append(unquote(urlsplit(item['path']).path).strip('/'))
        try:stars.append(parse_public_count(item['stars']))
        except ValueError:raise ValueError('Invalid rendered star count') from None
    checks['rendered_project_identities']=len(paths)==len(set(paths)) and all(p in refs for p in paths)
    if not checks['rendered_project_identities']:return checks
    # These tasks check directory navigation, filtering and sorting, not an
    # exact numeric answer. A valid rounded label must not become a runtime
    # error or an invented exact count. Check complete displayed values when
    # available; retain identity, collection and independent DB-order checks.
    checks['rendered_project_values']=all(
        not stars[i]['exact'] or stars[i]['value']==refs[p]['star_count']
        for i,p in enumerate(paths))
    access=spec.get('access_reference')
    scope=spec.get('scope','explore')
    if scope not in ('dashboard','explore'):raise ValueError('Unsupported project collection')
    if scope=='dashboard' and access is None:raise ValueError('Dashboard requires account authorization reference')
    allowed=set(access['authorized_project_ids' if scope=='dashboard' else 'project_ids']) if access is not None else {r['id'] for r in reference}
    pool=[r for r in reference if not r['archived'] and r['id'] in allowed]
    requested_page=query.get('page',['1'])[0]
    if not requested_page.isdecimal() or int(requested_page)<=0:return {**checks,'directory_parameters_unambiguous':False}
    number=int(requested_page)
    # Native pinned view has a fixed 20-row page size. Changing other filters
    # must not silently replace the requested collection.
    checks['directory_scope']=not any(query.get(k,[''])[0] for k in ('personal','owned','namespace_id','tag','topic')) and query.get('non_archived',['true'])==['true']
    current_path=urlsplit(url).path.rstrip('/')
    checks['directory_scope'] &= (current_path in ('','/dashboard/projects') if scope=='dashboard' else current_path in ('/explore','/explore/projects','/explore/projects/starred','/explore/projects/trending'))
    name=query.get('name',[''])[0]
    visibility=query.get('visibility_level',[''])[0]
    if kind=='search':
        needle=spec['text'].casefold()
        checks['requested_project_search']=name.casefold()==needle and state['query'].casefold()==needle
        checks['directory_scope'] &= not visibility
        pool=[r for r in pool if any(needle in (r[k] or '').casefold() for k in ('name','path','description'))]
    elif kind=='visibility':
        labels={20:'Public',10:'Internal',0:'Private'}
        accepted=spec['levels'];level=int(visibility) if visibility.isdecimal() else None
        checks['requested_project_visibility']=level in accepted and labels.get(level) in state['button_labels']
        checks['directory_scope'] &= not name
        pool=[r for r in pool if r['visibility_level']==level]
        checks['rendered_visibility_matches']=all((item.get('visibility') or '').startswith(labels.get(level,'INVALID')+' - ') for item in items)
    elif kind in ('stars','updated','explore','trending','page'):
        checks['directory_scope'] &= not name and not visibility
    else:raise ValueError('Unsupported project directory operation')
    if kind=='trending':
        pool=[r for r in pool if r['id'] in spec['trending_project_ids']]
        checks['requested_project_trending']=urlsplit(url).path.rstrip('/')=='/explore/projects/trending' and any(t.get('text')=='Trending' and t.get('path')=='/explore/projects/trending' for t in state['tabs'])
    expected_count=min(20,max(0,len(pool)-(number-1)*20))
    checks['matching_project_results']=len(paths)==expected_count and set(paths)<={r['path'] for r in pool}
    if kind=='search' and len(pool)<=20:checks['matching_project_results'] &= set(paths)=={r['path'] for r in pool}
    if kind in ('stars','updated'):
        # The pinned native UI calls its Updated date parameter
        # latest_activity_desc, but the observed ordering uses updated_at.
        field,label,param=('star_count','Most stars','stars_desc') if kind=='stars' else ('updated_at','Updated date','latest_activity_desc')
        tab=any(t.get('path')=='/explore/projects/starred' and t.get('text')=='Most stars' for t in state['tabs'])
        # Closed dropdown options are hidden; the visible native button carries
        # the current selection. Still require matching URL AND real DB order.
        requested=(query.get('sort')==[param] and label in state['button_labels']) or (kind=='stars' and urlsplit(url).path.rstrip('/')=='/explore/projects/starred' and tab)
        checks['requested_project_sort']=requested
        values=[refs[p][field] for p in paths]
        sorted_values=sorted([r[field] for r in pool],reverse=True)
        checks['project_values_in_order']=bool(values) and values==sorted_values[(number-1)*20:number*20]
    if kind=='explore':checks['explore_tab_active']=any(t.get('text')=='All' and t.get('path')=='/explore/projects' for t in state['tabs'])
    if kind=='page':
        # The private native snapshot fixes page membership and ordering. A
        # forged URL or a different slice of equally valid projects must fail.
        expected=spec.get('page_paths')
        target=spec.get('page_number')
        if (type(target) is not int or target<1 or spec.get('sort')!='name_asc'
                or not isinstance(expected,list) or not expected
                or any(not isinstance(p,str) or p not in refs for p in expected)
                or len(expected)!=len(set(expected)) or len(expected)>20):
            raise ValueError('Invalid native project-page reference')
        checks['requested_project_page']=(number==target and query.get('sort')==['name_asc']
                                         and 'Name' in state['button_labels'])
        checks['requested_page_projects']=paths==expected
        checks['explore_tab_active']=any(t.get('text')=='All' and t.get('path')=='/explore/projects' for t in state['tabs'])
    return checks
