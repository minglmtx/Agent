"""Private complete native starred membership and public directory binding."""
from urllib.parse import parse_qs,unquote,urlsplit
from .site_database import select_rows


def starred_reference(site, access, projects):
    # Keep every native membership row/column, including foreign users and
    # timestamps, in the independent before/after reference. Never update it.
    schema=select_rows(site,"SELECT column_name AS column_name,udt_name AS type_name FROM information_schema.columns WHERE table_schema='public' AND table_name='users_star_projects' ORDER BY ordinal_position")
    columns=[r['column_name']for r in schema]
    if len(columns)!=len(set(columns))or not {'user_id','project_id'}<=set(columns):raise ValueError('Complete native starred-membership schema unavailable')
    count=select_rows(site,'SELECT count(*)::bigint AS count FROM users_star_projects')[0]['count']
    if type(count)is not int or not 0<=count<=25000:raise ValueError('Bounded complete native starred membership required')
    rows=select_rows(site,'SELECT * FROM users_star_projects ORDER BY user_id,project_id')
    if len(rows)!=count or any(set(r)!=set(columns)for r in rows):raise ValueError('Complete all-column native starred membership unavailable')
    if select_rows(site,'SELECT count(*)::bigint AS count FROM users_star_projects')[0]['count']!=count:raise ValueError('Native membership changed while capturing')
    keys=[(r['user_id'],r['project_id'])for r in rows]
    if len(keys)!=len(set(keys))or any(type(u)is not int or type(p)is not int or u<1 or p<1 for u,p in keys):raise ValueError('Native unique membership identities required')
    allowed=set(access['project_ids']);by_id={r['id']:r for r in projects}
    own=[r['project_id']for r in rows if r['user_id']==access['user']['id'] and r['project_id']in allowed]
    if any(i not in by_id for i in own):raise ValueError('Actual starred project object unavailable')
    paths=sorted(by_id[i]['path']for i in own if not by_id[i]['archived'])
    return {'complete_users_star_projects':{'schema':schema,'row_count':count,'rows':rows,'columns_ignored':[]},'starred_project_paths':paths}


def starred_checks(state, private):
    url=urlsplit(state['url']);query=parse_qs(url.query,keep_blank_values=True)
    scope=(unquote(url.path).rstrip('/')=='/dashboard/projects/starred'
        and state.get('body_page')=='dashboard:projects:starred'
        and not set(query)-{'sort','page'}
        and all(len(set(v))==1 for v in query.values()))
    rows=state.get('projects')
    if not isinstance(rows,list):raise ValueError('Actual native starred project rows unavailable')
    paths=[unquote(urlsplit(r.get('path','')).path).strip('/')for r in rows]
    expected=set(private['starred_project_paths'])
    return {'native_starred_directory_scope':scope,
        'native_starred_row_identities':len(paths)==len(set(paths))and all(p in expected for p in paths),
        'native_starred_empty_state':bool(paths)==bool(expected)}
