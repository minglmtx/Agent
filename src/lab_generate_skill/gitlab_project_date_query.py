"""Native directory 'Updated' dates, separate from commit/activity timestamps.

Only a private saved-record reader and an independent public DOM reader. New
tasks still require live observability, negative controls and reset admission.
"""
from datetime import datetime, timezone
from urllib.parse import urlsplit
from .site_database import select_rows


def utc_date(value, *, database=False):
    if not isinstance(value, str):
        raise ValueError('Missing project timestamp')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        if not database:
            raise ValueError('Public timestamp must specify its timezone')
        # Native PostgreSQL projects.updated_at is stored as UTC without zone.
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).date().isoformat()


def validate(q):
    if (q.get('family') != 'gitlab_project_updated' or type(q.get('object_id')) is not int
            or q['object_id'] <= 0 or q.get('fields') != {'updated_date': 'string'}
            or not isinstance(q.get('project'), str) or not q['project']
            or q['project'].startswith('/') or '?' in q['project'] or '#' in q['project']):
        raise ValueError('Invalid native project-date query')


def reference(site, q):
    validate(q)
    rows = select_rows(site, "SELECT p.id,p.updated_at,r.path FROM projects p JOIN routes r "
                       "ON r.source_id=p.id AND r.source_type='Project' WHERE p.id=" + str(q['object_id']))
    if len(rows) != 1 or rows[0]['path'] != q['project']:
        raise ValueError('Project-date reference identity changed')
    return {'object_id': q['family']+':'+str(q['object_id']),
            'values': {'updated_date': utc_date(rows[0]['updated_at'], database=True)},
            'source_timestamp': rows[0]['updated_at']}


def ui_values(page, q):
    validate(q)
    if urlsplit(page.url).path not in ('/', '/dashboard/projects', '/explore', '/explore/projects'):
        raise ValueError('Native project directory required')
    rows = page.locator('.project-row').evaluate_all('''es=>es.map(e=>({
      path:e.querySelector('a.project')?.getAttribute('href'),
      times:[...e.querySelectorAll('time')].filter(t=>!!t.getClientRects().length).map(t=>({
        datetime:t.getAttribute('datetime'),context:t.parentElement.innerText
      }))
    }))''')
    matching = [r for r in rows if urlsplit(r.get('path') or '').path.strip('/') == q['project']]
    if len(matching) != 1:
        raise ValueError('Rendered project-date identity missing or ambiguous')
    times = matching[0]['times']
    if len(times) != 1 or not times[0]['context'].strip().startswith('Updated'):
        raise ValueError('Public Updated timestamp absent or ambiguous')
    return {'updated_date': utc_date(times[0]['datetime'])}
