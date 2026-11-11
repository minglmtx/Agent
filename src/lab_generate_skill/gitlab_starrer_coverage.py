"""Audit public user identities in selected AX observations across native pages.

Only explicit observations count. Goals, answers, older chat history, unselected
full AX, and the evaluator's private enumeration never count as actor exposure.
This evidence is necessary for 'view all', not a standalone success evaluator.
"""
import ast,json
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,unquote
from .document_observation import NODE
from .site_database import select_rows


def validate(spec):
    if not isinstance(spec.get('project'),str)or len(spec['project'].split('/'))!=2:
        raise ValueError('Explicit project path required')
    users=spec.get('users');pages=spec.get('pages')
    if not isinstance(users,list)or not users or not isinstance(pages,list)or not pages:
        raise ValueError('Complete public membership and pagination reference required')
    for row in users:
        if (not isinstance(row,dict)or type(row.get('id'))is not int or row['id']<=0
            or row.get('private_profile')is not False or any(not isinstance(row.get(k),str)or not row[k]for k in ('name','username'))):
            raise ValueError('Only identified public user profiles are supported')
    ids=[r['id']for r in users]
    if len(set(ids))!=len(ids)or len({r['username']for r in users})!=len(users):raise ValueError('Duplicate user reference')
    if any(not isinstance(page,list)or not page or any(type(i)is not int for i in page)for page in pages):
        raise ValueError('Invalid native page membership')
    flat=[i for page in pages for i in page]
    if len(set(flat))!=len(flat)or set(flat)!=set(ids):raise ValueError('Incomplete or duplicate pagination reference')
    return {r['id']:r for r in users}


def ax_names(text):
    result=[]
    for line in text.splitlines():
        node=NODE.match(line)
        if not node:continue
        try:name=ast.literal_eval(node.group(3))
        except (ValueError,SyntaxError):continue
        if isinstance(name,str):result.append((node.group(2),name))
    return result


def coverage(spec,observations,*,site_origin):
    refs=validate(spec);seen=set();accepted=[];origin=urlsplit(site_origin)
    if not isinstance(observations,list):raise ValueError('Recorded observations required')
    for index,row in enumerate(observations):
        if (not isinstance(row,dict)or row.get('observation_mode')not in ('full','viewport')
            or not isinstance(row.get('observation'),str)or not isinstance(row.get('url'),str)):
            raise ValueError('Malformed selected AX observation')
        u=urlsplit(row['url']);params=parse_qs(u.query,keep_blank_values=True)
        if ((u.scheme,u.netloc)!=(origin.scheme,origin.netloc)
            or unquote(u.path).rstrip('/')!='/'+spec['project']+'/-/starrers'
            or set(params)-{'page'}):continue
        page=params.get('page',['1'])
        if len(page)!=1 or not page[0].isdigit()or not 1<=int(page[0])<=len(spec['pages']):continue
        names=ax_names(row['observation']);links={name for role,name in names if role=='link'}
        labels={name for role,name in names if role=='StaticText'}
        # Name and account handle must both occur in the actual selected AX.
        # Restrict identities to this independently verified native page.
        observed={ident for ident in spec['pages'][int(page[0])-1]
                  if refs[ident]['name']in links and '@'+refs[ident]['username']in labels}
        seen.update(observed);accepted.append({'observation_index':index,'page':int(page[0]),'user_ids':sorted(observed)})
    return {'complete':seen==set(refs),'observed_user_ids':sorted(seen),'missing_user_ids':sorted(set(refs)-seen),
        'reference_user_count':len(refs),'observations':accepted}


def issued_observations(directory):
    """Read only completed real model requests; never substitute step/full AX."""
    observations=[]
    for path in sorted(Path(directory).glob('generation-*.json')):
        row=json.loads(path.read_text())
        if row.get('status')!='complete'or row.get('scripted_control'):continue
        messages=row.get('messages')
        if not isinstance(messages,list)or not messages or messages[-1].get('role')!='user':
            raise ValueError('Completed generation lacks selected observation request')
        body=json.loads(messages[-1]['content'])
        observations.append({key:body.get(key)for key in ('url','observation_mode','observation')})
    return observations


def verify_reference(site,spec):
    validate(spec)
    ident=spec.get('project_id')
    if type(ident)is not int or ident<=0:raise ValueError('Pinned project ID required')
    routes=select_rows(site,f"SELECT path FROM routes WHERE source_type='Project' AND source_id={ident}")
    if routes!=[{'path':spec['project']}]:raise ValueError('Starrer project route changed')
    users=select_rows(site,f'SELECT u.id,u.username,u.name,u.private_profile FROM users_star_projects s JOIN users u ON u.id=s.user_id WHERE s.project_id={ident} ORDER BY u.id')
    if users!=sorted(spec['users'],key=lambda r:r['id']):raise ValueError('Public starrer membership changed')


def read_starrers(page):
    return page.evaluate('''() => ({url:location.href,body_page:document.body.getAttribute('data-page'),
        project_ids:[...new Set([...document.querySelectorAll('[data-project-id]')].map(e=>e.getAttribute('data-project-id')))],
        users:[...document.querySelectorAll('a.js-user-link[data-user-id]')].filter(e=>e.getClientRects().length).map(e=>({
            id:e.getAttribute('data-user-id'),name:e.innerText.trim(),path:new URL(e.href).pathname}))})''')


def checks(spec,state,*,site_origin):
    refs=validate(spec)
    if (not isinstance(state,dict)or not isinstance(state.get('url'),str)or not isinstance(state.get('users'),list)
        or not isinstance(state.get('project_ids'),list)or not isinstance(state.get('body_page'),str)
        or not isinstance(state.get('issued_observations'),list)):
        raise ValueError('Missing starrer page or actual observation history')
    u=urlsplit(state['url']);origin=urlsplit(site_origin);params=parse_qs(u.query,keep_blank_values=True)
    page=params.get('page',['1'])
    identity=((u.scheme,u.netloc)==(origin.scheme,origin.netloc)
        and unquote(u.path).rstrip('/')=='/'+spec['project']+'/-/starrers'
        and not(set(params)-{'page'})and len(page)==1 and page[0].isdigit()
        and 1<=int(page[0])<=len(spec['pages'])and state['body_page']=='projects:starrers:index'
        and state['project_ids']==[str(spec['project_id'])])
    expected=[refs[i]for i in spec['pages'][int(page[0])-1]]if identity else []
    native=[{'id':str(r['id']),'name':r['name'],'path':'/'+r['username']}for r in expected]
    observed=coverage(spec,state['issued_observations'],site_origin=site_origin)
    return {'starrer_project_identity':identity,'starrer_native_page_content':identity and state['users']==native,
            'all_public_starrers_observed':observed['complete']}


FEEDBACK={'starrer_project_identity':'The current starrer page belongs to the requested project.',
    'starrer_native_page_content':'The current native user list matches the initialized public collection.',
    'all_public_starrers_observed':'All requested public user identities were included in the observations delivered during this attempt.'}
