"""Unified native lifecycle for explicit GitLab goals and typed read queries.

This optional adapter uses the normal runner's native hook slot. It does not
navigate, retry, rewrite observations, reveal an oracle, or score intermediate
actions. Two completed cold groups and full sixteen-table protection remain
mandatory. Unavailable native fields remain unavailable, never model failures.
"""
from copy import deepcopy
from datetime import date
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlsplit
from .source_revision_binding import binding, fingerprint, require_source_binding
from .browser_prompt_contract import ANSWER_VALUES_GUIDANCE
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .gitlab_native_read_runtime import full_snapshot
from .gitlab_navigation_goal_runtime import require_initialization
from .gitlab_native_csv_probe import auth_backup, restore_auth_metadata, protected_snapshot_session
from .gitlab_directory import project_reference, directory_access_reference, directory_checks, read_directory_page
from .gitlab_project_date_query import utc_date
from .gitlab_project_search import reference as search_reference, read_search, checks as search_checks
from .gitlab_section import read_section
from .query_record_sets import record_set_matches, negative_record_answers
from .admin_query_rules import parse_answer
from .io_utils import atomic_write_json

VERSION = 'gitlab-grouped-goal-runtime-v1'
PROOF_VERSION = 'gitlab-grouped-goal-two-cold-controls-v2-cache-certified'
QUERY_FAMILY = 'gitlab_grouped_goal_query'
QUERY_KINDS = {'updated_project_set', 'star_project_set',
               'literal_current_page_project_set', 'last_closed_merge_request', 'issue_updated_date', 'merge_request_latest_pipeline'}
NATIVE_KINDS = {'project_section', 'global_activity', 'tag_commit', 'project_search',
                'different_project_sort', 'all_project_tags', 'repository_root', 'project_clipboard', 'starred_directory',
                'repository_code_search', 'global_merge_request_search', 'search_scope_transition'}
KINDS = QUERY_KINDS | NATIVE_KINDS
SHA = re.compile(r'[0-9a-f]{64}')
PROJECT = re.compile(r'[\w.-]+(?:/[\w.-]+)+')

READ = r'''() => {
 const shown=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const main=document.querySelector('main.content,#content-body')||document.querySelector('main');
 return {url:location.href,title:document.title,body_page:document.body.dataset.page,
 account_id:window.gon?.current_user_id??null,main_text:main?.innerText||'',
 times:[...document.querySelectorAll('main time,#content-body time')].filter(shown).map(e=>({datetime:e.getAttribute('datetime'),context:e.parentElement.innerText})),
 issue_rows:[...document.querySelectorAll('[data-qa-selector="issue_container"],[data-qa-selector="issuable_container"][data-qa-issue-id]')].filter(shown).map(e=>({
   id:e.getAttribute('data-qa-issue-id')||e.getAttribute('data-id'),title:e.querySelector('a[data-qa-selector="issuable_title_link"],.issue-title a[href]')?.innerText.trim(),
   path:e.querySelector('a[data-qa-selector="issuable_title_link"],.issue-title a[href]')?.getAttribute('href'),
   updated_times:[...e.querySelectorAll('.issuable-timestamp time[datetime],[data-testid="issuable-timestamp"][title]')].filter(shown).map(t=>({datetime:t.getAttribute('datetime'),display_title:t.getAttribute('title'),context:t.hasAttribute('datetime')?t.parentElement.innerText:t.innerText}))})),
 projects:[...document.querySelectorAll('.project-row')].map(e=>({path:e.querySelector('a.project[href]')?.getAttribute('href'),name:e.querySelector('a.text-plain.js-prefetch-document[href]')?.innerText.trim(),description:(e.querySelector('.project-details .description,.project-description')?.innerText.trim()||'').replace(/\s+/g,' '),stars:e.querySelector('a.stars')?.innerText.trim(),times:[...e.querySelectorAll('time[datetime]')].map(t=>({datetime:t.getAttribute('datetime'),context:t.parentElement.innerText}))})),
 tag_links:[...document.querySelectorAll('main a[href],#content-body a[href]')].filter(shown).filter(e=>/\/-\/tags\//.test(e.getAttribute('href')||'')).map(e=>({text:e.innerText.trim(),href:e.getAttribute('href')})),
 next_links:[...document.querySelectorAll('.pagination a[href]')].filter(shown).filter(e=>/^Next\s*$/i.test(e.innerText)).map(e=>e.getAttribute('href')),
 capture_truncated:false};}'''


def public_query(spec):
    kind = spec['kind']
    if kind in ('updated_project_set', 'star_project_set', 'literal_current_page_project_set'):
        return {'family': QUERY_FAMILY, 'kind': kind, 'fields': {'projects': 'record_set'},
                'record_fields': {'projects': {'path': 'string'}},
                'field_meanings': {'projects': 'All requested full project paths; [] means no matches.'}}
    if kind == 'last_closed_merge_request':
        return {'family': QUERY_FAMILY, 'kind': kind, 'fields': {'closed_date': 'nullable_date'},
                'field_meanings': {'closed_date': 'UTC YYYY-MM-DD of the last closed merge request; JSON null if no closed merge requests exist.'}}
    if kind == 'merge_request_latest_pipeline':
        return {'family': QUERY_FAMILY, 'kind': kind, 'fields': {'pipeline_status': 'string'},
                'field_meanings': {'pipeline_status': 'Native status of the latest attached pipeline; no inferred success or result.'}}
    if kind == 'issue_updated_date':
        return {'family': QUERY_FAMILY, 'kind': kind, 'fields': {'updated_date': 'date'},
                'field_meanings': {'updated_date': 'The requested issue Updated date in UTC YYYY-MM-DD; Edited is a different field.'}}
    return None


def enabled(contract):
    if 'gitlab_grouped_goal' not in contract:
        return False
    spec = contract['gitlab_grouped_goal']
    if (contract.get('domain') != 'gitlab' or not isinstance(spec, dict)
            or spec.get('version') != VERSION or spec.get('kind') not in KINDS
            or contract.get('eligible_for_training') is not False
            or contract.get('completion') != {'family': 'gitlab_grouped_goal'}):
        raise ValueError('Explicit separately admitted GitLab normal goal required')
    binding(contract)
    if contract.get('query') != public_query(spec):
        # An absent query and query=None are both normal navigation declarations.
        if contract.get('query') is not None or public_query(spec) is not None:
            raise ValueError('Private native scope and public query schema differ')
    if any(contract.get(k) for k in ('gitlab_native_read', 'gitlab_navigation_goal',
            'preferences', 'clipboard', 'native_csv_export', 'repository_download',
            'project_creation', 'fork_creation', 'ref_creation', 'cart', 'vote')):
        raise ValueError('A normal grouped goal cannot mix another native lifecycle')
    if not isinstance(spec.get('username'), str) or not re.fullmatch(r'[\w.-]+', spec['username']):
        raise ValueError('Native source account required')
    if 'project' in spec and not PROJECT.fullmatch(spec['project']):
        raise ValueError('Native named project identity required')
    kind = spec['kind']
    if kind in ('project_section', 'tag_commit', 'all_project_tags', 'repository_root',
                'project_clipboard', 'last_closed_merge_request', 'issue_updated_date',
                'repository_code_search', 'merge_request_latest_pipeline') and 'project' not in spec:
        raise ValueError('Named native project is mandatory for this goal family')
    if kind in ('repository_code_search', 'global_merge_request_search', 'search_scope_transition') and (not isinstance(spec.get('term'), str) or not spec['term'].strip()):
        raise ValueError('Explicit native literal search required')
    if kind == 'merge_request_latest_pipeline' and (type(spec.get('iid')) is not int or spec['iid']<1):
        raise ValueError('Explicit native merge request IID required')
    if kind == 'repository_root' and not SHA.fullmatch(spec.get('native_rendered_readme_sha256', '')):
        raise ValueError('Actual complete native README identity required')
    if kind == 'updated_project_set':
        if date.fromisoformat(spec['date_start']) > date.fromisoformat(spec['date_end']):
            raise ValueError('Invalid inclusive deterministic date range')
    if kind == 'star_project_set' and (type(spec.get('threshold')) is not int or spec['threshold'] < 0):
        raise ValueError('Explicit native star threshold required')
    if kind == 'literal_current_page_project_set':
        members = spec.get('members')
        if (not isinstance(members, list) or not members or len(set(members)) != len(members)
                or any(not isinstance(p, str) or not PROJECT.fullmatch(p) for p in members)
                or not isinstance(spec.get('term'), str) or not spec['term']):
            raise ValueError('Frozen original-page members and literal criterion required')
    return True


def require_original_binding(contract, original, inventory):
    enabled(contract)
    return require_source_binding(contract, original, inventory, domain='gitlab')


def public_goal(contract):
    enabled(contract)
    q = public_query(contract['gitlab_grouped_goal'])
    if q is None:
        return contract['goal']
    # Deliberately avoid private paths, expected values, source IDs and controls.
    shapes = ''
    if 'record_fields' in q:
        shapes = ' projects is an unordered JSON array of records with exactly one string field, path. Include every requested project once; use [] for no matches.'
    elif q['fields'] == {'closed_date': 'nullable_date'}:
        shapes = ' closed_date is a UTC YYYY-MM-DD string, or JSON null only when no closed merge requests exist.'
    elif q['fields'] == {'pipeline_status': 'string'}:
        shapes = ' pipeline_status is the native pipeline status as a plain English string.'
    else:
        shapes = ' updated_date is a UTC YYYY-MM-DD string. Read Updated, not a related timestamp.'
    return (contract['goal']+'\nTo finish, output a browser finish action with an answer JSON object '
            'containing exactly these fields: '+', '.join(q['fields'])+'. '+ANSWER_VALUES_GUIDANCE+shapes)


def answer_field_spec(contract):
    """Use the same public query types as the native task description."""
    enabled(contract)
    query = public_query(contract['gitlab_grouped_goal'])
    return dict(query['fields']) if query else {}


def fields(contract):
    enabled(contract)
    query = public_query(contract['gitlab_grouped_goal'])
    return list(query['fields']) if query else []


def _project(site, path):
    rows = select_rows(site, "SELECT p.id,p.name,r.path FROM projects p JOIN routes r "
        "ON r.source_type='Project' AND r.source_id=p.id WHERE r.path='"+path.replace("'", "''")+"'")
    if len(rows) != 1:
        raise ValueError('Unique native target project unavailable')
    return rows[0]


def _git(site, ident, *args):
    digest = hashlib.sha256(str(ident).encode()).hexdigest()
    root = '/var/opt/gitlab/git-data/repositories/@hashed/'+digest[:2]+'/'+digest[2:4]+'/'+digest+'.git'
    response = site.command(['/opt/gitlab/embedded/bin/git', '--git-dir='+root, *args],
                            capture_output=True, text=True, timeout=45)
    if response.returncode:
        raise ValueError('Native immutable Git reference unavailable')
    return response.stdout.rstrip('\n')


def reference(site, contract):
    enabled(contract); spec = contract['gitlab_grouped_goal']; kind = spec['kind']
    access = directory_access_reference(site, spec['username'])
    result = {'kind': kind, 'account_id': access['user']['id']}
    if 'project' in spec:
        result['project'] = _project(site, spec['project'])
    if kind in ('updated_project_set', 'star_project_set', 'literal_current_page_project_set'):
        rows = [r for r in project_reference(site) if not r['archived'] and r['id'] in access['project_ids']]
        if kind == 'literal_current_page_project_set':
            by = {r['path']: r for r in rows}
            if not set(spec['members']) <= set(by):
                raise ValueError('Initial-page native project membership changed')
            rows = [by[p] for p in spec['members']]
        if kind == 'literal_current_page_project_set':
            displays = select_rows(site,"SELECT p.id,r.name AS native_display_name,p.description_html AS native_description_html FROM projects p JOIN routes r ON r.source_id=p.id AND r.source_type='Project' ORDER BY p.id")
            by_display = {r['id']:r['native_display_name'] for r in displays}
            if any(r['id'] not in by_display or not isinstance(by_display[r['id']],str) for r in rows):
                raise ValueError('Independent native display names unavailable')
            from .gitlab_public_query_bindings import native_description_text
            by_html={r['id']:r.get('native_description_html') for r in displays}
            rows = [{**r, 'native_display_name':by_display[r['id']],
                'native_description_html':by_html[r['id']],
                'native_description_text':native_description_text(r['description'],by_html[r['id']])}
                for r in rows]
        return collection_reference(spec, result, rows)
    if kind == 'starred_directory':
        from .gitlab_grouped_directory_navigation import starred_reference
        result.update(starred_reference(site, access, project_reference(site)))
    elif kind == 'last_closed_merge_request':
        ident = result['project']['id']
        rows = select_rows(site, f'SELECT id,iid,title,state_id FROM merge_requests WHERE target_project_id={ident} AND state_id=2 ORDER BY id')
        if rows:
            raise ValueError('Nonempty closure history needs an independently verified closure timestamp association')
        result.update(closed_rows=rows, values={'closed_date': None})
    elif kind == 'merge_request_latest_pipeline':
        rows = select_rows(site, 'SELECT id,iid,title,head_pipeline_id FROM merge_requests WHERE target_project_id='
            +str(result['project']['id'])+' AND iid='+str(spec['iid']))
        if len(rows)!=1:
            raise ValueError('Unique native merge request unavailable')
        mr=rows[0]; pipelines=select_rows(site,'SELECT id,project_id,merge_request_id,status,created_at FROM ci_pipelines WHERE merge_request_id='+str(mr['id'])+' OR id='+str(mr['head_pipeline_id'] or 0)+' ORDER BY id DESC')
        if not pipelines or any(r['project_id'] != result['project']['id'] or not isinstance(r['status'],str) for r in pipelines):
            raise ValueError('Actual attached native pipeline/status unavailable')
        result.update(merge_request=mr,pipelines=pipelines,values={'pipeline_status':pipelines[0]['status']})
    elif kind == 'repository_code_search':
        head=_git(site,result['project']['id'],'rev-parse','HEAD')
        # Native literal code search uses case-insensitive matching. Require the
        # actual returned native file set to agree before accepting controls.
        digest=hashlib.sha256(str(result['project']['id']).encode()).hexdigest()
        root='/var/opt/gitlab/git-data/repositories/@hashed/'+digest[:2]+'/'+digest[2:4]+'/'+digest+'.git'
        matched=site.command(['/opt/gitlab/embedded/bin/git','--git-dir='+root,'grep','-l','-i','-F', '-e', spec['term'],head,'--'],capture_output=True,text=True,timeout=45)
        if matched.returncode not in (0,1):
            raise ValueError('Independent immutable code search unavailable')
        paths=sorted({line[len(head)+1:] for line in matched.stdout.splitlines() if line.startswith(head+':')})
        result.update(git_head=head,git_match_paths=paths)
    elif kind in ('global_merge_request_search','search_scope_transition'):
        result['literal_query']=spec['term']
    elif kind == 'issue_updated_date':
        rows = select_rows(site, 'SELECT id,iid,title,updated_at,last_edited_at FROM issues WHERE project_id='
            +str(result['project']['id'])+" AND title='"+spec['title'].replace("'", "''")+"'")
        if len(rows) != 1:
            raise ValueError('Unique named issue unavailable')
        result.update(issue=rows[0], values={'updated_date': utc_date(rows[0]['updated_at'], database=True)})
    elif kind == 'tag_commit':
        result['tag_commit'] = _git(site, result['project']['id'], 'rev-parse', 'refs/tags/'+spec['tag']+'^{commit}')
        if not re.fullmatch(r'[0-9a-f]{40}', result['tag_commit']):
            raise ValueError('Native requested tag has no unique commit')
    elif kind == 'all_project_tags':
        result['git_tags'] = sorted(_git(site, result['project']['id'], 'tag', '--list').splitlines())
    elif kind == 'repository_root':
        result['git_head'] = _git(site, result['project']['id'], 'rev-parse', 'HEAD')
        result['git_root_paths'] = _git(site, result['project']['id'], 'ls-tree', '--name-only', result['git_head']).splitlines()
        result['native_rendered_readme_sha256'] = spec['native_rendered_readme_sha256']
    elif kind == 'project_clipboard':
        result['clipboard_expected'] = str(result['project']['id'])
    elif kind == 'project_search':
        result['search'] = search_reference(site, spec['username'], spec['term'])
    elif kind == 'different_project_sort':
        result['directory'] = {'kind': 'stars', 'scope': 'dashboard',
                               'reference': project_reference(site), 'access_reference': access}
    return result


def collection_reference(spec, base, rows):
    kind = spec['kind']; rows = deepcopy(rows)
    paths = [r['path'] for r in rows]
    if len(paths) != len(set(paths)):
        raise ValueError('Duplicate native project identity')
    if kind == 'updated_project_set':
        chosen = [r['path'] for r in rows if spec['date_start'] <= utc_date(r['updated_at'], database=True) <= spec['date_end']]
    elif kind == 'star_project_set':
        if any(type(r.get('star_count')) is not int or r['star_count'] < 0 for r in rows):
            raise ValueError('Exact native star count unavailable')
        chosen = [r['path'] for r in rows if r['star_count'] > spec['threshold']]
    elif kind == 'literal_current_page_project_set':
        if paths != spec['members']:
            raise ValueError('Original fixed-page ordering differs')
        chosen = [r['path'] for r in rows if spec['term'].casefold() in (r.get('native_display_name',r['name'])+' '+r.get('native_description_text',(r['description'] or ''))).casefold()]
    else:
        raise ValueError('Unsupported native collection criterion')
    return {**deepcopy(base), 'source_rows': rows,
            'values': {'projects': [{'path': p} for p in sorted(chosen)]}}


def validate_public_collection(spec, private, captures):
    """Admission-only complete public DOM versus independent native SQL fields."""
    if not isinstance(captures, list) or not captures:
        raise ValueError('Actual complete native collection captures required')
    rows = []
    for capture in captures:
        if capture.get('capture_truncated') is not False or not isinstance(capture.get('projects'), list):
            raise ValueError('Partial native collection capture')
        u = urlsplit(capture.get('url', '')); params = parse_qs(u.query, keep_blank_values=True)
        if (u.path != '/explore/projects' or set(params)-{'non_archived', 'sort', 'page'}
                or params.get('non_archived', ['true']) != ['true']
                or params.get('sort', ['name_asc']) != ['name_asc']
                or capture.get('account_id') != private['account_id']):
            raise ValueError('Actual native collection scope/account differs')
        rows.extend(capture['projects'])
    paths = [unquote(urlsplit(r.get('path', '')).path).strip('/') for r in rows]
    private_rows = private['source_rows']; expected = {r['path']: r for r in private_rows}
    if len(paths) != len(set(paths)) or set(paths) != set(expected):
        raise ValueError('Complete native collection membership differs')
    if spec['kind'] == 'literal_current_page_project_set' and paths != spec['members']:
        raise ValueError('Observed original fixed-page membership/order differs')
    from .public_counts import parse_public_count
    for path, public in zip(paths, rows):
        actual = expected[path]
        if spec['kind'] == 'updated_project_set':
            timestamp = single_updated_timestamp(public.get('times', []))
            if utc_date(timestamp) != utc_date(actual['updated_at'], database=True):
                raise ValueError('Public Updated field absent or differs from private semantics')
        elif spec['kind'] == 'star_project_set':
            displayed = parse_public_count(public.get('stars'))
            if displayed['exact'] and displayed['value'] != actual['star_count']:
                raise ValueError('Displayed star count differs from native record')
            # Rounded k/M labels suffice only if the threshold classification
            # is unambiguous and agrees with the exact independent count.
            if (displayed['value'] > spec['threshold']) != (actual['star_count'] > spec['threshold']):
                raise ValueError('Rounded public count crosses the requested threshold')
    if spec['kind'] == 'literal_current_page_project_set':
        if any(public.get('name') != expected[path].get('native_display_name',expected[path]['name']) or public.get('description','') != expected[path].get('native_description_text',(expected[path]['description'] or '')) for path,public in zip(paths,rows)):
            raise ValueError('Public display names/descriptions differ from native route records')
        public_matches = sorted(path for path, public in zip(paths, rows)
            if spec['term'].casefold() in (public.get('name', '')+' '+public.get('description', '')).casefold())
        if [{'path': p} for p in public_matches] != private['values']['projects']:
            raise ValueError('Public literal result identities differ from the independent complete fixed-page criterion')
    return True


def single_updated_timestamp(times):
    """Collapse duplicated renderings of one field, never conflicting values."""
    instants = {}
    for row in times:
        if not isinstance(row, dict) or not row.get('context', '').strip().startswith('Updated'):
            continue
        raw = row.get('datetime')
        if not isinstance(raw, str):
            raise ValueError('Public Updated timestamp missing')
        stamp = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('Public Updated timestamp timezone missing')
        instants[stamp] = raw
    if len(instants) != 1:
        raise ValueError('Native Updated field missing or conflicting')
    return next(iter(instants.values()))


def read_native(page, kind):
    state = page.evaluate(READ)
    state['section'] = read_section(page)
    if kind in ('repository_code_search','global_merge_request_search','search_scope_transition','merge_request_latest_pipeline'):
        from .gitlab_grouped_native_search import read as read_extended
        state['extended'] = read_extended(page)
    if kind == 'project_search':
        state['search'] = read_search(page)
    if kind in ('different_project_sort','starred_directory'):
        state['directory'] = read_directory_page(page)
    if kind == 'last_closed_merge_request':
        from .gitlab_issuable_list import read_issuable_list
        state['issuables'] = read_issuable_list(page)
    if kind == 'repository_root':
        from .gitlab_repository import READ as repository_read, READY
        repo = page.evaluate(repository_read)
        repo['url'] = page.url
        repo['wait_status'] = 'ready' if page.evaluate(READY) else 'content_not_ready'
        state['repository'] = repo
    if kind == 'project_clipboard':
        from .gitlab_clipboard import read
        state['clipboard'] = read(page)
    return state


def page_checks(page, private, site_origin):
    if (not isinstance(page, dict) or type(page.get('http_status')) is not int
            or not isinstance(page.get('url'), str)
            or any(type(page.get(k)) is not bool for k in ('login_page', 'error_page'))):
        raise ValueError('Complete native terminal page health unavailable')
    if not 200 <= page['http_status'] < 500:
        raise ValueError('Native transport/server error')
    native = page.get('gitlab_grouped_goal')
    if not isinstance(native, dict) or native.get('url') != page['url']:
        raise ValueError('Coherent native terminal capture unavailable')
    checks = {'valid_native_page': valid_initial_page(page, site_origin=site_origin)}
    if private['kind'] != 'project_clipboard':
        checks['bound_native_account'] = native.get('account_id') == private['account_id']
    return checks


def native_checks(contract, page, private, *, observations=(), control_mode=False):
    spec = contract['gitlab_grouped_goal']; kind = spec['kind']; state = page['gitlab_grouped_goal']
    checks = {'native_main_content': isinstance(state.get('main_text'), str) and bool(state['main_text'].strip())}
    path = unquote(urlsplit(page['url']).path).rstrip('/')
    project = private.get('project')
    if project and kind not in ('project_clipboard','repository_code_search'):
        section = state.get('section')
        if not isinstance(section, dict):
            raise ValueError('Native project identity capture unavailable')
        checks['bound_target_project'] = (section.get('project_ids') == [str(project['id'])]
            and '/'+project['path'] in {r.get('path', '').rstrip('/') for r in section.get('breadcrumbs', [])})
        if not checks['bound_target_project']:
            return checks
    if kind in ('repository_code_search','global_merge_request_search','search_scope_transition'):
        from .gitlab_grouped_native_search import navigation_checks
        checks.update(navigation_checks(spec,state,private,observations,control_mode=control_mode))
    elif kind == 'project_section':
        checks['requested_native_section'] = path == '/'+project['path']+spec['suffix']
        prefixes = {'/-/metrics': 'projects:metrics_dashboard:', '/-/wikis/home': 'projects:wikis:',
                    '/-/packages': 'projects:packages:', '/-/snippets': 'projects:snippets:', '/-/usage_quotas':'projects:usage_quotas:'}
        checks['native_section_identity'] = isinstance(state.get('body_page'), str) and state['body_page'].startswith(prefixes[spec['suffix']])
    elif kind == 'starred_directory':
        from .gitlab_grouped_directory_navigation import starred_checks
        checks.update(starred_checks(state, private))
    elif kind == 'global_activity':
        checks['global_activity_scope'] = path == '/dashboard/activity' and bool(re.match(r'^Activity .*Dashboard.*GitLab$', state.get('title', '')))
    elif kind == 'tag_commit':
        checks['requested_immutable_commit'] = path == '/'+project['path']+'/-/commit/'+private['tag_commit'] and state.get('body_page') == 'projects:commit:show'
    elif kind == 'project_search':
        checks.update(search_checks(private['search'], state.get('search')))
    elif kind == 'different_project_sort':
        checks.update(directory_checks(private['directory'], state.get('directory'), page['url']))
    elif kind == 'all_project_tags':
        checks['native_tag_section'] = path == '/'+project['path']+'/-/tags'
        checked = complete_tag_coverage(contract, private, observations, require_issued=not control_mode)
        checks.update(checked)
    elif kind == 'repository_root':
        checks['native_named_repository_root'] = path == '/'+project['path'] and state.get('body_page') == 'projects:show'
        repo = state.get('repository')
        if not isinstance(repo, dict):
            raise ValueError('Complete native repository capture unavailable')
        prefix = '/'+project['path']+'/-/'
        names = []
        for link in repo.get('tree_links', []):
            href = unquote(urlsplit(link.get('href', '')).path)
            match = re.fullmatch(re.escape(prefix)+r'(?:tree|blob)/[^/]+/(.+)', href)
            if match:
                names.append(match[1])
        from .gitlab_repository import content_digest
        checks['native_repository_loaded'] = repo.get('loading') is False and repo.get('wait_status') == 'ready'
        checks['complete_immutable_root_entries'] = len(names) == len(set(names)) and set(names) == set(private['git_root_paths'])
        checks['pinned_native_commit_visible'] = '/'+project['path']+'/-/commit/'+private['git_head'] in {
            unquote(urlsplit(r.get('href', '')).path) for r in repo.get('commit_links', [])}
        checks['complete_native_readme_content'] = any(isinstance(t, str) and t.strip()
            and content_digest(t) == private['native_rendered_readme_sha256'] for t in repo.get('content', []))
    elif kind == 'project_clipboard':
        state = state.get('clipboard')
        if not isinstance(state, dict) or not isinstance(state.get('value'), str):
            raise ValueError('Actual bound browser clipboard capture unavailable')
        checks['requested_project_id_copied'] = state['value'] == private['clipboard_expected']
    return checks


def complete_tag_coverage(contract, private, observations, *, require_issued=True):
    """Only genuinely issued pages count. Wrong intermediate pages may recover."""
    target = '/'+private['project']['path']+'/-/tags'
    accepted = {}; tags = set()
    for row in observations or ():
        state = row.get('native') if isinstance(row, dict) else None
        if require_issued and row.get('acknowledged') is not True:
            continue
        if not isinstance(state, dict) or state.get('capture_truncated') is not False:
            continue
        url = urlsplit(state.get('url', '')); params = parse_qs(url.query, keep_blank_values=True)
        if unquote(url.path).rstrip('/') != target or set(params)-{'page'}:
            continue
        number = params.get('page', ['1'])
        if len(number) != 1 or not number[0].isdigit() or int(number[0]) < 1:
            continue
        if state.get('account_id') != private['account_id']:
            continue
        public = []
        for link in state.get('tag_links', []):
            href = unquote(urlsplit(link.get('href', '')).path)
            if not href.startswith(target+'/') or href[len(target)+1:] != link.get('text'):
                continue
            public.append(link['text'])
        if len(public) != len(set(public)):
            continue
        number = int(number[0]); nexts = state.get('next_links')
        if not isinstance(nexts, list):
            continue
        if nexts:
            if len(set(nexts)) != 1:
                continue
            destination = urlsplit(nexts[0]); query = parse_qs(destination.query, keep_blank_values=True)
            if (unquote(destination.path).rstrip('/') != target or query != {'page': [str(number+1)]}
                    or destination.fragment or destination.scheme or destination.netloc):
                continue
        old = accepted.get(number)
        if old is not None and old['next'] != nexts:
            # Conflicting page membership/pagination must not be unioned.
            continue
        accepted[number] = {'tags': set(public) | (old['tags'] if old else set()), 'next': nexts}
    last = next((n for n in sorted(accepted) if accepted[n]['next'] == []), None)
    complete = last is not None and set(range(1, last+1)) <= set(accepted)
    if complete:
        sequence = [t for n in range(1, last+1) for t in accepted[n]['tags']]
        tags = set(sequence)
        complete = len(sequence) == len(tags)
    return {'native_all_tag_pages_issued': complete,
            'complete_immutable_tag_membership': complete and tags == set(private['git_tags'])}


def evaluate(contract, page, private, *, site_origin, answer=None, observations=(), runtime_error=None, control_mode=False):
    enabled(contract)
    def unknown(reason):
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': reason}
    if runtime_error:
        return unknown('Environment or inference error')
    try:
        checks = page_checks(page, private, site_origin)
        if not all(checks.values()):
            return {'version': VERSION, 'status': 'failure', 'reward': 0.0,
                    'checks': checks, 'reason': None}
        q = public_query(contract['gitlab_grouped_goal'])
        if q is None:
            checks.update(native_checks(contract, page, private, observations=observations, control_mode=control_mode))
        else:
            try:
                value = parse_answer(answer)
                checks['answer_schema'] = set(value) == set(q['fields'])
            except (ValueError, TypeError):
                value = {}; checks['answer_schema'] = False
            if set(private.get('values', {})) != set(q['fields']):
                raise ValueError('Complete independent native answer reference unavailable')
            for key, kind in q['fields'].items():
                actual, expected = value.get(key), private['values'][key]
                if kind == 'record_set':
                    checks['answer_'+key] = record_set_matches(actual, expected, q['record_fields'][key])
                elif kind == 'string':
                    checks['answer_'+key] = checks['answer_schema'] and isinstance(actual,str) and actual == expected
                elif kind in ('date', 'nullable_date'):
                    checks['answer_'+key] = (checks['answer_schema'] and actual is None and expected is None
                        if kind == 'nullable_date' and expected is None else
                        isinstance(actual, str) and bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', actual)) and actual == expected)
                else:
                    raise ValueError('Unsupported native typed answer protocol')
    except (KeyError, TypeError, ValueError):
        return unknown('Complete native identity/reference evidence unavailable')
    passed = all(checks.values())
    return {'version': VERSION, 'status': 'success' if passed else 'failure',
            'reward': float(passed), 'checks': checks, 'reason': None}


def control_expectations(contract, private, controls):
    q = public_query(contract['gitlab_grouped_goal'])
    if q is None:
        if contract['gitlab_grouped_goal']['kind'] == 'project_clipboard':
            return {'no_op': 'failure', 'navigation_only': 'failure', 'positive': 'success',
                    'saved_then_home': 'success', 'wrong_project_copy': 'failure', '404': 'failure', 'login': 'failure'}
        return {name: ('success' if name == 'positive' else 'failure') for name in controls}
    expected = {'positive': 'success', 'no_answer': 'failure', 'wrong_value': 'failure',
                '404': 'failure', 'login': 'failure'}
    expected.update({name: 'failure' for name in negative_record_answers(q, private['values'])})
    return expected


def require_group_initialization(cycle):
    # Reuse only identical, fully verified group evidence within one prepare.
    # Archive and manifest bytes are still checked on every source gate.
    from .gitlab_scoped_initialization_validation import validate
    return validate(cycle, _require_group_initialization)


def _require_group_initialization(cycle):
    """Validate common native initialization and full actual rendering effects."""
    import gitlab_native_wiki_cache_init as cache
    import gitlab_issue_cache_certification as issue_cache
    for key in ('native_before_initialization','protected_before','protected_after'):
        full_snapshot(cycle.get(key))
    record=cache.parse_result('LAB_NATIVE_WIKI_CACHE_INIT_BEGIN\n'+json.dumps(cycle.get('native_initialization_record'))+'\nLAB_NATIVE_WIKI_CACHE_INIT_END')
    effects=cache.verify_effects(cycle.get('columns_before'),cycle.get('columns_after'),
        cycle['native_before_initialization'],cycle['protected_before'],record)
    for columns,full in ((cycle['columns_before'],cycle['native_before_initialization']),
            (cycle['columns_after'],cycle['protected_before'])):
        if columns['columns']!=full['projects']['columns']or columns['row_count']!=full['projects']['rows']:
            raise ValueError('Complete native initialization columns differ')
    if cycle.get('native_initialization_effects')!=effects:
        raise ValueError('Exact complete native initialization effects required')
    from .gitlab_grouped_evidence_archive import load as load_issue_evidence
    evidence=load_issue_evidence(cycle.get('issue_cache_evidence'))
    proof=issue_cache.verify(evidence['before'],evidence['after'],cycle['protected_before'],
        cycle['protected_after'],evidence['witness'],evidence['native'])
    if proof!=cycle.get('native_issue_cache_certification'):
        raise ValueError('Native issue cache certificate differs from all-row evidence')
    return proof


def require_admission(contract, proof):
    enabled(contract)
    if (not isinstance(proof, dict) or proof.get('version') != PROOF_VERSION
            or proof.get('contract_fingerprint') != fingerprint(contract)
            or proof.get('source_binding') != binding(contract)
            or proof.get('formal_preinference_lifecycle_verified') is not True
            or type(proof.get('actor_attempts')) is not int or proof['actor_attempts'] != 0
            or type(proof.get('api_calls')) is not int or proof['api_calls'] != 0):
        raise ValueError('Exact actual no-model grouped normal proof required')
    cycles = proof.get('cycles')
    if not isinstance(cycles, list) or len(cycles) != 2:
        raise ValueError('Two complete fresh native groups required')
    ids = [c.get('fresh_instance_id') for c in cycles]
    if any(not isinstance(i, str) or not SHA.fullmatch(i) for i in ids) or len(set(ids)) != 2:
        raise ValueError('Two actually distinct native instances required')
    for cycle in cycles:
        require_group_initialization(cycle)
        group = cycle.get('group_source_ids')
        if (not isinstance(group, list) or not 1 <= len(group) <= 32
                or len(set(group)) != len(group) or contract['source_task_id'] not in group
                or cycle.get('all_group_controls_completed') is not True
                or cycle.get('private_reference_after') != cycle.get('private_reference')):
            raise ValueError('Whole actual cold group completion/reference protection required')
        controls = cycle.get('controls')
        if not isinstance(controls, dict):
            raise ValueError('Actual replayable native controls required')
        expected = control_expectations(contract, cycle['private_reference'], controls)
        if set(controls) != set(expected) or not {'positive', '404', 'login'} <= set(controls):
            raise ValueError('All normal positive, negative and transport controls required')
        if public_query(contract['gitlab_grouped_goal']) is not None:
            qualify_query_evidence(contract, cycle)
        elif (contract['gitlab_grouped_goal']['kind'] != 'project_clipboard'
                and ('initial' not in controls or not {'wrong_object', 'wrong_filter'} & set(controls))):
            raise ValueError('Native navigation needs actual initial and wrong scope controls')
        for name, control in controls.items():
            if proof.get('terminal_fresh_full16_required') is True:
                from .gitlab_terminal_group_protection import require_fresh_terminal
                require_fresh_terminal(control, cycle)
            actual = evaluate(contract, control['page'], cycle['private_reference'],
                site_origin=control['site_origin'], answer=control.get('answer'),
                observations=control.get('observations', []), control_mode=True)['status']
            # An already-satisfied initial navigation state is legitimate.
            wanted = ('success' if name == 'initial' and cycle.get('initial_goal_already_satisfied') is True else expected[name])
            if actual != wanted:
                raise ValueError('Actual native control differs: '+name)
    for key in ('native_before_initialization', 'protected_before', 'native_initialization_effects', 'private_reference'):
        if cycles[0][key] != cycles[1][key]:
            raise ValueError('Independent cold initialization/reference differs: '+key)
    return deepcopy(cycles[0]['private_reference'])


def qualify_query_evidence(contract, cycle):
    spec = contract['gitlab_grouped_goal']; private = cycle['private_reference']
    public = cycle.get('public_observability_evidence')
    if spec['kind'] in ('updated_project_set', 'star_project_set', 'literal_current_page_project_set'):
        return validate_public_collection(spec, private, public)
    if not isinstance(public, dict):
        raise ValueError('Actual public native field capture required')
    if spec['kind'] == 'merge_request_latest_pipeline':
        from .gitlab_grouped_native_search import qualify_pipeline
        return qualify_pipeline(spec,private,public)
    if spec['kind'] == 'last_closed_merge_request':
        from .gitlab_issuable_query import observed_values
        pr = private['project']
        q = {'family': 'gitlab_issuable_count', 'collection': {'kind': 'merge_requests', 'state': 'closed',
            'username': spec['username'], 'project_path': pr['path'], 'assigned_to_current_user': False},
            'user_id': private['account_id'], 'project_id': pr['id'], 'fields': {'count': 'integer'},
            'reference_path': '/'+pr['path']+'/-/merge_requests?scope=all&state=closed'}
        if (private.get('closed_rows') != [] or private.get('values') != {'closed_date': None}
                or observed_values(q, public['issuables'], public['url']) != {'count': 0}):
            raise ValueError('No closed history must have a verified native zero/empty state')
        return True
    if spec['kind'] == 'issue_updated_date':
        from .gitlab_public_query_bindings import qualify_issue_updated
        return qualify_issue_updated(private, public)
    raise ValueError('Unimplemented native query observability')


class GroupedGoalHooks:
    def __init__(self, contract, proof, directory):
        self.reference = require_admission(contract, proof)
        self.contract, self.proof, self.directory = deepcopy(contract), deepcopy(proof), Path(directory)
        self.context = self.initial_page = None
        self.prepared = self.scored = False
        self.timeline = []
        self.final_answer = None

    def prepare(self, site, username):
        if self.prepared or username != self.contract['gitlab_grouped_goal']['username']:
            raise ValueError('One bound native reset/account required')
        import gitlab_native_wiki_cache_init as cache
        folder = self.directory/'grouped-goal-initialization'; folder.mkdir(parents=True, exist_ok=False)
        cold, baseline, effects = cache.initialize(site, folder)
        expected = self.proof['cycles'][0]; actual = reference(site, self.contract)
        if any(x != y for x, y in ((cold, expected['native_before_initialization']),
                (baseline, expected['protected_before']), (effects, expected['native_initialization_effects']),
                (actual, self.reference))):
            raise ValueError('Actual cold normal reset/reference differs from admitted grouped CPU evidence')
        self.site, self.before, self.auth = site, baseline, auth_backup(site, username)
        from gitlab_issue_cache_normal_protection import NativeIssueProtection
        self.issue_protection=NativeIssueProtection(site,username,self.directory/'normal-issue-cache-protection',full_baseline=baseline)
        from .gitlab_grouped_evidence_archive import load as load_issue_evidence
        expected_issues=load_issue_evidence(expected['issue_cache_evidence'])['before']
        if self.issue_protection.before!=expected_issues:
            raise ValueError('Actual whole native issue reset differs from both admitted cold groups')
        self.prepared = True

    def attach(self, context):
        if not self.prepared or self.context is not None:
            raise ValueError('One prepared browser context required')
        self.context = context
        self.issue_protection.attach(context)
        if self.contract['gitlab_grouped_goal']['kind'] == 'project_clipboard':
            context.grant_permissions(['clipboard-read', 'clipboard-write'], origin=self.site.url)

    def observe_initial(self, page):
        if self.initial_page is not None or page.context is not self.context:
            raise ValueError('One bound original/derived initial page required')
        declared, actual = urlsplit(self.contract['start_path']), urlsplit(page.url)
        if (declared.path, parse_qs(declared.query)) != (actual.path, parse_qs(actual.query)):
            raise ValueError('Actual initial native page differs from explicit source/revision start')
        spec = self.contract['gitlab_grouped_goal']
        if spec['kind'] == 'literal_current_page_project_set':
            native = read_native(page, spec['kind'])
            members = [unquote(urlsplit(r.get('path', '')).path).strip('/') for r in native['projects']]
            if members != spec['members']:
                raise ValueError('Actual current-page members/order differs from both cold controls')
        if spec['kind'] == 'project_clipboard':
            from .gitlab_clipboard import prepare
            if prepare(page, self.site.url) != {'value': ''}:
                raise ValueError('Bound browser clipboard baseline differs from the CPU proof')
        self.issue_protection.observe(page)
        self.initial_page = page

    def record(self, page, *, event='issued_observation'):
        if self.initial_page is None or page.context is not self.context:
            raise ValueError('Only bound issued native observations may be recorded')
        self.issue_protection.observe(page)
        native = read_native(page, self.contract['gitlab_grouped_goal']['kind'])
        row = {'event': event, 'acknowledged': False, 'native': native}
        if self.contract['gitlab_grouped_goal']['kind'] == 'all_project_tags':
            row['native_document_tag_links'] = deepcopy(native['tag_links'])
            row['issued_tag_names'] = []
        self.timeline.append(row)
        # Private evaluator observations never modify or augment model inputs.
        atomic_write_json(self.directory/'grouped-goal-private-observations.json', self.timeline)

    def acknowledge_issued(self, actual_ax):
        if not self.timeline or not isinstance(actual_ax, str) or not actual_ax.strip():
            raise ValueError('Actual nonempty issued accessibility tree required')
        row = self.timeline[-1]
        if row['event'] == 'terminal':
            raise ValueError('Terminal-private capture is not an actor-issued observation')
        issued_sha = hashlib.sha256(actual_ax.encode()).hexdigest()
        if row.get('issued_ax_sha256') == issued_sha:
            return
        row['acknowledged'] = True
        row['issued_ax_sha256'] = issued_sha
        if self.contract['gitlab_grouped_goal']['kind'] == 'all_project_tags':
            # A full private DOM capture must not count off-viewport tag labels
            # as information actually issued to the actor. Scrolling naturally
            # exposes remaining labels; the collector never performs it.
            names = {m.group(1) for m in re.finditer(r"\blink\s+['\"]([^'\"]+)['\"]", actual_ax)}
            names |= set(row['issued_tag_names']); row['issued_tag_names'] = sorted(names)
            row['native']['tag_links'] = [r for r in row['native_document_tag_links'] if r['text'] in names]
        atomic_write_json(self.directory/'grouped-goal-private-observations.json', self.timeline)

    def provide_trace(self, trace):
        if not isinstance(trace, dict) or self.scored:
            raise ValueError('Actual rollout trace must precede terminal judgment')
        from .admin_pilot import final_answer
        self.final_answer = final_answer(trace)

    def capture_terminal(self, page, terminal):
        self.record(page, event='terminal')
        terminal['gitlab_grouped_goal'] = deepcopy(self.timeline[-1]['native'])
        atomic_write_json(self.directory/'terminal-grouped-goal.json', terminal)

    def score_terminal(self, site, page, *, answer=None, runtime_error=None):
        if not self.prepared or self.scored or site is not self.site:
            raise ValueError('One terminal judgment after verified reset required')
        self.scored = True; errors = []; after = actual = certification = None
        try:
            restore_auth_metadata(site, self.auth)
            after = protected_snapshot_session(site, self.directory/'grouped-goal-full16-progress.jsonl')
            full_snapshot(after); actual = reference(site, self.contract)
            certification=self.issue_protection.certify_terminal(after)
        except Exception as error:
            from .runtime_diagnostics import failure_diagnostic
            errors.append(failure_diagnostic(error, 'grouped_goal_full16_and_reference'))
        integrity = bool(not errors and certification is not None and certification.get('protection_certified')is True and actual == self.reference)
        atomic_write_json(self.directory/'grouped-goal-full16-protection.json',
            {'before': self.before, 'after': after, 'reference_before': self.reference,
             'reference_after': actual, 'raw_full_snapshot_unchanged':after==self.before,
             'protection_certified':integrity,'native_issue_cache_certification':certification,'errors':errors,
             'complete16': True, 'columns_ignored': []})
        if runtime_error or not integrity:
            judgment = {'version': VERSION, 'status': 'unknown', 'reward': None,
                        'checks': {'complete_native_protection_certified': integrity},
                        'reason': 'Environment, inference or native reference integrity error'}
        else:
            judgment = evaluate(self.contract, page, self.reference, site_origin=site.url,
                                answer=self.final_answer if answer is None else answer, observations=self.timeline)
            judgment['checks']['complete_native_protection_certified'] = True
        return judgment, integrity

    def close(self):
        pass


def feedback(judgment):
    meanings = {'valid_native_page': 'The final page is a valid local native page.',
        'bound_native_account': 'The task account is preserved.',
        'bound_target_project': 'The requested project is displayed.',
        'requested_native_section': 'The requested native section is displayed.',
        'native_section_identity': 'The native page identifies the requested section.',
        'native_main_content': 'Native page content is loaded.',
        'global_activity_scope': 'Activity across projects is displayed.',
        'requested_immutable_commit': 'The commit belonging to the requested tag is displayed.',
        'native_all_tag_pages_issued': 'All native tag-list pages were visited.',
        'complete_immutable_tag_membership': 'The complete requested tag set was displayed.',
        'native_named_repository_root': 'The requested repository root is displayed.',
        'native_repository_loaded': 'Native repository content is loaded.',
        'complete_immutable_root_entries': 'The complete pinned root file and directory set is displayed.',
        'pinned_native_commit_visible': 'The requested immutable repository revision is displayed.',
        'complete_native_readme_content': 'The complete native README content is displayed.',
        'requested_project_id_copied': 'The bound browser clipboard contains the requested project ID.',
        'answer_schema': 'The final answer follows the public field schema.',
        'answer_projects': 'The requested complete project set is correct.',
        'answer_closed_date': 'The requested closure date or native absence is correct.',
        'answer_updated_date': 'The requested Updated date is correct.',
        'complete_native_protection_certified': 'All original native rows and content are preserved; any normal rendering cache effect is exactly certified.'}
    return {'status': judgment.get('status'), 'reward': judgment.get('reward'),
            'reason': judgment.get('reason'), 'checks': [
                {'name': k, 'passed': v, 'condition': meanings.get(k, 'The declared native scope condition is satisfied.')}
                for k, v in judgment.get('checks', {}).items()],
            'action_sequence_provided': False, 'reference_values_provided': False}
