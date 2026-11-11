"""Release answers from saved released_at, independently checked against native UI.

Creation/commit timestamps are never release dates. UI reads are private control
evidence; neither reference records nor navigation plans are actor instructions.
"""
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit,unquote
from .site_database import select_rows
from .gitlab_project_date_query import utc_date
from .browser_page_wait import settle_gitlab_capture


def validate(q):
    kind=q.get('kind');project=q.get('project')
    if (q.get('family')!='gitlab_release' or kind not in ('released_date','latest')
            or type(q.get('object_id'))is not int or q['object_id']<=0
            or not isinstance(project,str) or not re.fullmatch(r'[\w.-]+(?:/[\w.-]+)+',project)
            or any(part in ('.','..')for part in project.split('/'))
            or q.get('reference_path')!='/'+project+'/-/releases'
            or q.get('fields')!=({'released_date':'string'}if kind=='released_date'else {'tag':'string_choice'})):
        raise ValueError('Invalid native release query')
    if kind=='released_date' and (not isinstance(q.get('tag'),str) or not q['tag']):
        raise ValueError('Explicit release tag required')


def reference(site,q):
    validate(q)
    identity=select_rows(site,"SELECT id,path FROM routes WHERE source_type='Project' AND source_id="+str(q['object_id']))
    if len(identity)!=1 or identity[0]['path']!=q['project']:raise ValueError('Release project identity changed')
    rows=select_rows(site,'SELECT id,tag,released_at FROM releases WHERE project_id='+str(q['object_id'])+' ORDER BY released_at DESC,id')
    if not rows:raise ValueError('Project has no release records')
    timestamps=[datetime.fromisoformat(r['released_at'].replace('Z','+00:00'))for r in rows]
    timestamps=[t.replace(tzinfo=timezone.utc)if t.tzinfo is None else t.astimezone(timezone.utc)for t in timestamps]
    if q['kind']=='latest':
        newest=max(timestamps);values={'tag':sorted(r['tag']for r,t in zip(rows,timestamps)if t==newest)}
    else:
        matching=[r for r in rows if r['tag']==q['tag']]
        if len(matching)!=1:raise ValueError('Missing or ambiguous release tag')
        values={'released_date':utc_date(matching[0]['released_at'],database=True)}
    return {'object_id':'gitlab-release:'+str(q['object_id'])+':'+q['kind']+':'+q.get('tag',''),
            'values':values,'source_records':rows}


def public_timestamp(label,title):
    if not isinstance(label,str) or label.strip()!='Released' or not isinstance(title,str):raise ValueError('Expected Released, not Created or a commit date')
    # GitLab's native tooltip displays local time and an explicit GMT offset.
    return datetime.strptime(title,'%b %d, %Y %I:%M%p GMT%z').astimezone(timezone.utc)


def ui_values(page,q):
    validate(q)
    u=urlsplit(page.url)
    if u.path.rstrip('/')!=q['reference_path'] or u.query:raise ValueError('Unfiltered native project release list required')
    settle_gitlab_capture(page)
    data=page.evaluate(r'''() => ({page:document.body.dataset.page,
      sort:document.querySelector('[data-testid="releases-sort"]')?.innerText.trim(),
      rows:[...document.querySelectorAll('.release-block')].map(e=>({tag:e.querySelector('.js-tag-info a')?.innerText.trim(),
        tag_url:e.querySelector('.js-tag-info a')?.href,
        label:e.querySelector('.js-author-date-info > span')?.innerText.trim(),
        times:[...e.querySelectorAll('.js-author-date-info > span[title]')].map(t=>t.title)}))})''')
    if data['page']!='projects:releases:index' or data['sort']!='Released date' or not data['rows']:
        raise ValueError('Loaded release-date sorted list missing')
    rows=data['rows']
    if len({r['tag']for r in rows})!=len(rows):raise ValueError('Duplicate release identity')
    dates=[]
    for r in rows:
        if not r['tag'] or len(r['times'])!=1:raise ValueError('Public release timestamp absent or ambiguous')
        tag_url=urlsplit(r.get('tag_url')or '')
        if (tag_url.scheme,tag_url.netloc)!=(u.scheme,u.netloc) or unquote(tag_url.path)!='/'+q['project']+'/-/tags/'+r['tag']:
            raise ValueError('Release tag points to another project or object')
        dates.append(public_timestamp(r['label'],r['times'][0]))
    if dates!=sorted(dates,reverse=True):raise ValueError('Release list is not newest first')
    if q['kind']=='latest':return {'tag':rows[0]['tag']}
    matching=[t for r,t in zip(rows,dates)if r['tag']==q['tag']]
    if len(matching)!=1:raise ValueError('Requested release is not present on the captured page')
    return {'released_date':matching[0].date().isoformat()}
