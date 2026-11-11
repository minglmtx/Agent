"""Queries over an original, fixed directory page; private DB and public DOM readers.

The member set is captured before any actor runs and verified in two resets.
Actor navigation never redefines the meaning of 'this page'.
"""
from urllib.parse import urlsplit, parse_qsl, unquote
from .site_database import select_rows
from .gitlab_project_date_query import utc_date
from .public_counts import parse_public_count

SCHEMAS = {
    'stars_above': {'count': 'integer'},
    'most_stars': {'projects': 'record_set'},
    'most_open_issues': {'project': 'string_choice'},
    'latest_updated': {'updated_date': 'string'},
    'all_projects': {'projects': 'record_set'},
    'compare_open_issues': {'projects': 'record_subset'},
}


def page_key(url):
    u = urlsplit(url)
    return (u.path or '/', tuple(sorted(parse_qsl(u.query, keep_blank_values=True))))


def database_rows(site):
    return select_rows(site, "SELECT p.id,r.path,p.star_count,p.updated_at,"
        "(SELECT count(*) FROM issues i WHERE i.project_id=p.id AND i.state_id=1) AS open_issues "
        "FROM projects p JOIN routes r ON r.source_id=p.id AND r.source_type='Project' ORDER BY p.id")


def public_project_paths(page):
    """Read identities without requiring unrelated star/issue/date fields.

    A name-list task remains readable when the native site abbreviates a
    numeric count. Numeric queries still use the strict public_rows reader.
    """
    raw = page.locator('.project-row').evaluate_all(
        "es=>es.map(e=>e.querySelector('a.project[href]')?.getAttribute('href'))")
    if not raw or any(not isinstance(x, str) or not x.startswith('/') or x.startswith('//') for x in raw):
        raise ValueError('Missing native project identities')
    paths = [unquote(urlsplit(x).path).strip('/') for x in raw]
    if any(not x or len(x.split('/')) < 2 for x in paths) or len(paths) != len(set(paths)):
        raise ValueError('Empty or duplicate native project identities')
    return paths


def public_rows(page, required_fields=None):
    required_fields = set(required_fields) if required_fields is not None else {'star_count','open_issues','updated_date'}
    if not required_fields <= {'star_count','open_issues','updated_date'}:
        raise ValueError('Unknown public directory field')
    rows = page.locator('.project-row').evaluate_all('''es=>es.map(e=>{
      const visible=n=>!!n.getClientRects().length;
      const texts=s=>[...e.querySelectorAll(s)].filter(visible).map(n=>n.innerText.trim());
      return {path:e.querySelector('a.project')?.getAttribute('href'),
        stars:texts('a.stars'),issues:texts('a.issues'),
        times:[...e.querySelectorAll('time')].filter(visible).map(t=>({
          datetime:t.getAttribute('datetime'),context:t.parentElement.innerText}))};
    })''')
    result = []
    exact_issue_counts = None
    for row in rows:
        path = unquote(urlsplit(row.get('path') or '').path).strip('/')
        if not path:
            raise ValueError('Incomplete public directory row')
        # Responsive markup may contain duplicates, but their values must agree.
        def number(values):
            if not values or len(set(values)) != 1:
                raise ValueError('Ambiguous public directory number')
            return parse_public_count(values[0])
        item={'path':path}
        for field, key in (('star_count','stars'),('open_issues','issues')):
            if field not in required_fields:
                continue
            parsed = number(row[key])
            if parsed['exact']:
                item[field] = parsed['value']
            elif field == 'open_issues':
                if exact_issue_counts is None:
                    from .gitlab_exact_directory import public_issue_rows
                    exact_rows, _ = public_issue_rows(page)
                    original_paths = [unquote(urlsplit(r.get('path') or '').path).strip('/') for r in rows]
                    if [r['path'] for r in exact_rows] != original_paths:
                        raise ValueError('Public issue reader changed directory membership/order')
                    exact_issue_counts = {r['path']: r['open_issues'] for r in exact_rows}
                item[field] = exact_issue_counts[path]
            else:
                raise ValueError('Exact public star_count unavailable for rounded display '
                                 + repr(parsed['display'])
                                 + '; a verified native count or complete enumeration is required')
        if 'updated_date' in required_fields:
            times = row['times']
            if len(times) != 1 or not times[0]['context'].strip().startswith('Updated'):
                raise ValueError('Missing native Updated timestamp')
            item['updated_date']=utc_date(times[0]['datetime'])
        result.append(item)
    if not result or len({r['path'] for r in result}) != len(result):
        raise ValueError('Empty or duplicate native project collection')
    return result


def normalize_database(rows):
    return [{'path': r['path'], 'star_count': int(r['star_count']),
             'open_issues': int(r['open_issues']),
             'updated_date': utc_date(r['updated_at'], database=True)} for r in rows]


def validate(q):
    if q.get('family') != 'gitlab_collection' or q.get('kind') not in SCHEMAS:
        raise ValueError('Unsupported collection query')
    if q.get('fields') != SCHEMAS[q['kind']]:
        raise ValueError('Wrong collection answer schema')
    members = q.get('members')
    if not isinstance(members, list) or not members or any(not isinstance(x, str) or not x for x in members) or len(set(members)) != len(members):
        raise ValueError('Fixed original page membership is required')
    if q['kind'] == 'stars_above' and (type(q.get('threshold')) is not int or q['threshold'] < 0):
        raise ValueError('Explicit nonnegative star threshold required')
    if q['kind'] in ('most_stars','all_projects') and q.get('record_fields') != {'projects': {'path': 'string'}}:
        raise ValueError('Project set must contain full project paths')
    if q['kind']=='compare_open_issues':
        if q.get('record_fields')!={'projects':{'path':'string','open_issues':'integer'}} or q.get('minimum_records')!={'projects':2} or len(members)<2:
            raise ValueError('Comparison requires at least two distinct project issue counts')
    if not isinstance(q.get('reference_path'), str) or page_key(q['reference_path'])[0] not in ('/', '/explore', '/explore/projects', '/dashboard/projects'):
        raise ValueError('Original directory page is required')


def selected_rows(q, rows):
    validate(q)
    by_path = {r['path']: r for r in rows}
    if len(by_path) != len(rows) or not set(q['members']) <= by_path.keys():
        raise ValueError('Missing or duplicate collection identities')
    return [by_path[p] for p in q['members']]


def aggregate(q, rows):
    rows = selected_rows(q, rows)
    if q['kind']=='all_projects':
        return {'projects':[{'path':r['path']} for r in rows]}
    if q['kind']=='compare_open_issues':
        return {'projects':[{'path':r['path'],'open_issues':r['open_issues']} for r in rows]}
    if q['kind'] == 'stars_above':
        return {'count': sum(r['star_count'] > q['threshold'] for r in rows)}
    if q['kind'] == 'latest_updated':
        return {'updated_date': max(r['updated_date'] for r in rows)}
    key = 'star_count' if q['kind'] == 'most_stars' else 'open_issues'
    maximum = max(r[key] for r in rows)
    paths = sorted(r['path'] for r in rows if r[key] == maximum)
    return {'projects': [{'path': p} for p in paths]} if q['kind'] == 'most_stars' else {'project': paths}


def reference(site, q):
    raw = selected_rows(q, database_rows(site))
    rows = normalize_database(raw)
    return {'object_id': 'gitlab_collection:'+q['reference_path'],
            'values': aggregate(q, rows), 'source_rows': raw}


def ui_values(page, q):
    validate(q)
    if page_key(page.url) != page_key(q['reference_path']):
        raise ValueError('Public page is not the original collection')
    required={'stars_above':{'star_count'},'most_stars':{'star_count'},
              'most_open_issues':{'open_issues'},'compare_open_issues':{'open_issues'},
              'latest_updated':{'updated_date'}}
    rows = ([{'path':path} for path in public_project_paths(page)]
            if q['kind']=='all_projects' else public_rows(page,required[q['kind']]))
    if [r['path'] for r in rows] != q['members']:
        raise ValueError('Original page membership/order changed')
    if q['kind'] == 'latest_updated':
        # A private datetime attribute alone is insufficient for an AX actor.
        titles = page.locator('.project-row time:visible').evaluate_all(
            "es=>es.map(e=>e.getAttribute('title')||e.getAttribute('data-original-title'))")
        cdp = page.context.new_cdp_session(page)
        try:
            names = {n.get('name', {}).get('value', '')
                     for n in cdp.send('Accessibility.getFullAXTree')['nodes'] if not n.get('ignored')}
        finally:
            cdp.detach()
        if len(titles) != len(rows) or any(not title or title not in names for title in titles):
            raise ValueError('Absolute Updated dates are not accessible to the AX actor')
    values = aggregate(q, rows)
    if q['kind'] == 'most_open_issues':
        values['project'] = values['project'][0]
    return values
