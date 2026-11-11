"""Read-only original GitLab public-field identity; never actor strategy."""
from datetime import datetime
import re
from urllib.parse import unquote,urlsplit
from .gitlab_project_date_query import utc_date

def native_updated_timestamp(times):
    if not isinstance(times,list):raise ValueError('Actual Updated field rows required')
    instants={}
    for row in times:
        if not isinstance(row,dict)or not isinstance(row.get('context'),str):
            raise ValueError('Typed public timestamp record required')
        # Creation, editing, closing and arbitrary prose mentioning updated
        # are different native fields. Duplicate renderings of the exact same
        # timestamp are harmless; two different timestamps remain ambiguous.
        if not re.match(r'^updated\b',row['context'].strip(),re.I):continue
        raw=row.get('datetime')
        if isinstance(raw,str):
            value=datetime.fromisoformat(raw.replace('Z','+00:00'))
        else:
            # Native Vue list renders the absolute timestamp in this scoped
            # component's tooltip title, not a <time datetime> element.
            title=row.get('display_title')
            if not isinstance(title,str) or not re.fullmatch(r'[A-Z][a-z]{2} [0-9]{1,2}, [0-9]{4} [0-9]{1,2}:[0-9]{2}(?:am|pm) GMT[+-][0-9]{4}',title):
                raise ValueError('Public Updated timestamp missing or unsupported')
            value=datetime.strptime(title,'%b %d, %Y %I:%M%p GMT%z')
            raw=value.isoformat()
        if value.tzinfo is None:raise ValueError('Public Updated timezone missing')
        instants[value]=raw
    if len(instants)!=1:raise ValueError('Native Updated field missing or conflicting')
    return next(iter(instants.values()))

def qualify_issue_updated(private,public):
    if not isinstance(public,dict)or public.get('capture_truncated')is not False:
        raise ValueError('Complete native public issue capture required')
    if public.get('account_id')!=private['account_id']:
        raise ValueError('Bound native issue account differs')
    project=private['project'];issue=private['issue']
    base='/'+project['path']+'/-/issues';target=base+'/'+str(issue['iid'])
    path=unquote(urlsplit(public.get('url','')).path).rstrip('/')
    if path==target and public.get('body_page')=='projects:issues:show':
        timestamp=native_updated_timestamp(public.get('times'))
    elif path==base and public.get('body_page')=='projects:issues:index':
        rows=public.get('issue_rows')
        if not isinstance(rows,list):raise ValueError('Actual native issue list rows unavailable')
        matches=[r for r in rows if isinstance(r,dict)and unquote(urlsplit(r.get('path','')).path).rstrip('/')==target]
        if len(matches)!=1:raise ValueError('Unique exact requested issue list row required')
        row=matches[0]
        if row.get('id')!=str(issue['id'])or row.get('title')!=issue['title']:
            raise ValueError('Actual issue ID/title differs from requested native object')
        timestamp=native_updated_timestamp(row.get('updated_times'))
    else:raise ValueError('Requested native issue detail or list page required')
    if utc_date(timestamp)!=private['values']['updated_date']:
        raise ValueError('Actual Updated field differs from independent issue.updated_at')
    return True

COPY_SELECTOR='[data-qa-selector="project_id_content"] [data-clipboard-text]'
def native_project_id_copy_control(page,*,expected_value=None):
    # The native project home template scopes this control separately from
    # README code blocks, clone URLs, and other clipboard buttons. This helper
    # only identifies a CPU control; it neither clicks nor reads private data.
    area=page.locator('[data-qa-selector="project_id_content"]')
    if area.count()!=1:raise ValueError('Unique native project-ID metadata required')
    text=area.inner_text();ids=re.findall(r'\bProject ID:\s*([1-9][0-9]*)\b',text)
    if len(ids)!=1:raise ValueError('Unique displayed native project ID required')
    buttons=page.locator(COPY_SELECTOR);matches=[]
    for index in range(buttons.count()):
        button=buttons.nth(index)
        if button.is_visible()and button.get_attribute('data-clipboard-text')==ids[0]:
            bid=button.get_attribute('bid')
            if isinstance(bid,str)and bid:matches.append(bid)
    if len(matches)!=1 or(expected_value is not None and str(expected_value)!=ids[0]):
        raise ValueError('Unique coherent native project-ID copy control required')
    return matches[0]


def native_description_text(source_markdown, native_html):
    """Project actual stored native HTML projection, never rerender Markdown.

    The pinned native project-list template calls markdown_field(project,
    :description). A missing stored native HTML for nonempty content remains
    unavailable; callers must not silently substitute raw Markdown. All source
    columns stay in the independent full-table protection.
    """
    from bs4 import BeautifulSoup
    from .gitlab_rendered_markdown_v4 import rendered_prose
    if source_markdown is None or source_markdown == '':
        if native_html not in (None, ''):
            raise ValueError('Empty native description has contradictory rendered content')
        return ''
    if not isinstance(source_markdown,str) or not isinstance(native_html,str) or not native_html.strip():
        raise ValueError('Independent stored native rendered description unavailable')
    root=BeautifulSoup(native_html,'html.parser')
    if root.find(['script','style']):
        raise ValueError('Native description contains non-content executable/style elements')
    return rendered_prose(root)
