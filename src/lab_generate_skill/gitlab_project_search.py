"""Equivalent native global/Explore project searches for explicit short queries.

Reference membership is access-scoped and checked before/after execution.
This adapter requires the complete matching set to fit one native page; it
never treats the first page of a larger result collection as complete.
"""
import re
from urllib.parse import urlsplit,parse_qs,unquote
from .gitlab_directory import directory_access_reference
from .site_database import select_rows


def validate(spec):
    if (not isinstance(spec,dict)or not isinstance(spec.get('term'),str)
        or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 .-]{0,79}',spec['term'])
        or not isinstance(spec.get('username'),str)or not spec['username']
        or type(spec.get('user_id'))is not int or spec['user_id']<=0):
        raise ValueError('Explicit native project search scope required')
    rows=spec.get('projects')
    if not isinstance(rows,list)or not 1<=len(rows)<=20:raise ValueError('Complete nonempty single-page project search reference required')
    if any(type(r.get('id'))is not int or r['id']<=0 or r.get('archived')is not False
        or any(not isinstance(r.get(k),str)or not r[k]for k in ('path','name'))for r in rows):
        raise ValueError('Invalid native project identities')
    if len({r['id']for r in rows})!=len(rows)or len({r['path']for r in rows})!=len(rows):raise ValueError('Duplicate project search reference')


def reference(site,username,term):
    if not isinstance(term,str)or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 .-]{0,79}',term):raise ValueError('Unsupported native literal search term')
    access=directory_access_reference(site,username);ids=','.join(str(int(i))for i in access['project_ids'])
    if not ids:raise ValueError('Account has no accessible projects')
    term_sql="'%"+term.replace("'","''")+"%'"
    rows=select_rows(site,"SELECT p.id,p.name,p.description,p.archived,r.path FROM projects p JOIN routes r ON r.source_id=p.id AND r.source_type='Project' WHERE p.id IN ("+ids+") AND (p.name ILIKE "+term_sql+" OR p.description ILIKE "+term_sql+" OR r.path ILIKE "+term_sql+") ORDER BY p.id")
    return {'term':term,'username':username,'user_id':access['user']['id'],'projects':rows}


def verify_reference(site,spec):
    validate(spec)
    if reference(site,spec['username'],spec['term'])!=spec:raise ValueError('Accessible matching project set changed')


def read_search(page):
    return page.evaluate(r'''() => {
      const shown=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
      return {url:location.href,user_id:window.gon?.current_user_id,
        fields:[...document.querySelectorAll('input[name=search],input[name=name]')].filter(shown).map(e=>({name:e.name,value:e.value})),
        active_scopes:[...document.querySelectorAll('a.nav-link.active[href]')].filter(e=>shown(e)&&new URL(e.href).pathname==='/search').map(e=>e.getAttribute('href')),
        projects:[...document.querySelectorAll('.project-row')].filter(shown).map(e=>{
          // a.project is the avatar (e.g. "B"), not the project title.
          // Require one visible native title and agreement with its avatar route.
          const avatar=e.querySelector('a.project[href]');
          const titles=[...e.querySelectorAll('a.text-plain.js-prefetch-document[href]')].filter(shown);
          const a=titles.length===1?titles[0]:null;
          const same=!!a&&!!avatar&&a.getAttribute('href')===avatar.getAttribute('href');
          return {path:same?a.getAttribute('href'):null,name:same?a.innerText.trim():null};
        })};
    }''')


def checks(spec,state):
    validate(spec)
    if (not isinstance(state,dict)or not isinstance(state.get('url'),str)
        or any(not isinstance(state.get(k),list)for k in ('fields','active_scopes','projects'))):
        raise ValueError('Missing native project search state')
    u=urlsplit(state['url']);query=parse_qs(u.query,keep_blank_values=True)
    unambiguous=all(len(set(v))==1 for v in query.values());q={k:v[0]for k,v in query.items()}
    global_search=u.path.rstrip('/')=='/search';directory=u.path.rstrip('/')in ('/explore','/explore/projects')
    term=spec['term'].casefold();key='search'if global_search else'name'
    entered=[r.get('value')for r in state['fields']if r.get('name')==key]
    result={'project_search_scope':unambiguous and (global_search or directory) and state.get('user_id')==spec['user_id'],
        'project_search_query_applied':q.get(key,'').casefold()==term and len(entered)==1 and isinstance(entered[0],str)and entered[0].casefold()==term}
    if global_search:
        result['project_search_scope'] &= q.get('scope','projects')=='projects' and not any(v for k,v in q.items()if k not in ('search','scope','page')) and q.get('page','1')=='1'
        links=[parse_qs(urlsplit(v).query)for v in state['active_scopes']if isinstance(v,str)]
        result['project_search_scope'] &= len(links)==1 and links[0].get('scope')==['projects'] and [s.casefold()for s in links[0].get('search',[])]==[term]
    else:
        result['project_search_scope'] &= not any(v for k,v in q.items()if k not in ('name','sort','page','non_archived')) and q.get('page','1')=='1' and q.get('non_archived','true')=='true'
    expected={r['path']:r for r in spec['projects']};seen=[];valid=True
    for row in state['projects']:
        link=row.get('path');name=row.get('name')
        if not isinstance(link,str)or not link.startswith('/')or link.startswith('//')or not isinstance(name,str):valid=False;continue
        path=unquote(urlsplit(link).path).strip('/');seen.append(path)
        valid &= path in expected and name.split('/')[-1].strip()==expected[path]['name'] and not urlsplit(link).query and not urlsplit(link).fragment
    result['complete_matching_projects_displayed']=valid and len(seen)==len(set(seen)) and set(seen)==set(expected)
    return result


FEEDBACK={'project_search_scope':'The native project search uses the requested account and project scope without unrelated filters.',
    'project_search_query_applied':'The requested search text is entered and applied.',
    'complete_matching_projects_displayed':'The complete matching set of project identities is displayed.'}
