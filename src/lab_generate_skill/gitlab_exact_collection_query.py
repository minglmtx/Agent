"""Exact public issue-count queries with frozen page or full-directory scope."""
from urllib.parse import urljoin, urlsplit, parse_qs
import re

from .gitlab_exact_directory import public_issue_rows
from .gitlab_directory import directory_access_reference
from .gitlab_collection_query import page_key
from .site_database import select_rows


def validate(q):
    if q.get('family')!='gitlab_exact_issue_collection' or q.get('kind') not in ('most_open_issues','compare_open_issues'):
        raise ValueError('Unsupported exact issue collection query')
    if q.get('scope') not in ('initial_page','all_accessible_nonarchived'):
        raise ValueError('Explicit original collection scope required')
    members=q.get('members')
    if not isinstance(members,list) or not members or any(not isinstance(p,str) or not re.fullmatch(r'[\w.-]+(?:/[\w.-]+)+',p) for p in members) or len(members)!=len(set(members)):
        raise ValueError('Unique frozen project identities required')
    if type(q.get('user_id')) is not int or q['user_id']<=0 or not re.fullmatch(r'[\w.-]+',q.get('username','')):
        raise ValueError('Frozen native account required')
    u=urlsplit(q['reference_path']);params=parse_qs(u.query,keep_blank_values=True)
    if u.scheme or u.netloc or u.fragment or u.path!='/explore/projects' or set(params)-{'non_archived','sort','page'}:
        raise ValueError('Unsupported directory URL')
    if params.get('non_archived')!=['true'] or params.get('sort')!=['name_asc']:
        raise ValueError('Directory scope must be explicitly non-archived, name order')
    page=params.get('page',['1'])
    if len(page)!=1 or not page[0].isdigit() or int(page[0])<1 or (q['scope']=='all_accessible_nonarchived' and page!=['1']):
        raise ValueError('Invalid initial page')
    shape={'path':'string'};kind='record_set'
    if q['kind']=='compare_open_issues':
        shape['open_issues']='integer';kind='record_subset'
        if len(members)<2 or q.get('minimum_records')!={'projects':2}:
            raise ValueError('Comparison requires at least two projects')
    if q.get('fields')!={'projects':kind} or q.get('record_fields')!={'projects':shape}:
        raise ValueError('Invalid exact collection answer schema')


def aggregate(q,rows):
    validate(q)
    by_path={r['path']:r for r in rows}
    if len(by_path)!=len(rows) or set(by_path)!=set(q['members']):
        raise ValueError('Collection membership differs from frozen scope')
    if any(type(r['open_issues']) is not int or r['open_issues']<0 for r in rows):
        raise ValueError('Missing exact issue count')
    if q['kind']=='compare_open_issues':
        return {'projects':[{'path':p,'open_issues':by_path[p]['open_issues']}for p in sorted(by_path)]}
    maximum=max(r['open_issues']for r in rows)
    return {'projects':[{'path':p}for p in sorted(by_path)if by_path[p]['open_issues']==maximum]}


def reference(site,q):
    validate(q);access=directory_access_reference(site,q['username'])
    if access['user']['id']!=q['user_id']:raise ValueError('Account identity changed')
    rows=select_rows(site,"SELECT p.id,r.path,p.archived,"
        "(SELECT count(*) FROM issues i WHERE i.project_id=p.id AND i.state_id=1) AS open_issues "
        "FROM projects p JOIN routes r ON r.source_id=p.id AND r.source_type='Project' ORDER BY p.id")
    allowed=[r for r in rows if not r['archived'] and r['id'] in access['project_ids']]
    if not set(q['members']) <= {r['path'] for r in allowed}:raise ValueError('Target projects missing or inaccessible')
    if q['scope']=='all_accessible_nonarchived' and {r['path']for r in allowed}!=set(q['members']):
        raise ValueError('Accessible directory membership changed')
    selected=[r for r in allowed if r['path']in q['members']]
    return {'object_id':'gitlab-exact-issues:'+q['scope']+':'+q['reference_path'],
            'values':aggregate(q,selected),'source_rows':selected,'user_id':q['user_id']}


def ui_values(page,q):
    validate(q)
    if page_key(page.url)!=page_key(q['reference_path']):raise ValueError('Wrong initial directory scope')
    if page.evaluate('() => window.gon?.current_user_id')!=q['user_id']:raise ValueError('Wrong browser account')
    origin=urlsplit(page.url);seen=set();rows=[]
    for _ in range(50):
        key=page_key(page.url)
        if key in seen:raise ValueError('Directory pagination loop')
        seen.add(key);current,_=public_issue_rows(page);rows.extend(current)
        if q['scope']=='initial_page':
            if [r['path']for r in rows]!=q['members']:raise ValueError('Initial page membership/order changed')
            break
        links=[e for e in page.get_by_role('link',name=re.compile(r'^Next\s*$')).all()if e.is_visible()]
        if not links:break
        if len(links)!=1:raise ValueError('Ambiguous native pagination')
        target=urljoin(page.url,links[0].get_attribute('href'));u=urlsplit(target);params=parse_qs(u.query,keep_blank_values=True)
        if u.netloc!=origin.netloc or u.scheme!=origin.scheme or u.path!='/explore/projects' or u.fragment:
            raise ValueError('Pagination leaves local directory')
        if set(params)!={'page','sort','non_archived'} or params['sort']!=['name_asc'] or params['non_archived']!=['true'] or len(params['page'])!=1 or not params['page'][0].isdigit():
            raise ValueError('Pagination changed filters')
        response=page.goto(target,wait_until='domcontentloaded',timeout=60000)
        if not response or response.status!=200:raise ValueError('Directory page unavailable')
    else:raise ValueError('Directory page budget exhausted')
    return aggregate(q,rows)
