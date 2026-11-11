"""Read-only issue/MR counts, with independent native scope and account checks."""
import re
from urllib.parse import urlsplit, parse_qs
from .gitlab_issuable_list import list_reference, read_issuable_list
from .site_query_rules import reference_fingerprint


def validate(q):
    spec = q['collection']
    if q.get('family') != 'gitlab_issuable_count' or set(spec) != {
            'kind', 'state', 'username', 'project_path', 'assigned_to_current_user'}:
        raise ValueError('Unsupported issuable query scope')
    if spec['kind'] not in ('issues', 'merge_requests') or spec['state'] not in ('opened', 'closed', 'merged', 'all'):
        raise ValueError('Unsupported collection or state')
    if spec['kind'] == 'issues' and spec['state'] == 'merged':
        raise ValueError('Issues have no merged state')
    if not re.fullmatch(r'[\w.-]+', spec['username']) or type(spec['assigned_to_current_user']) is not bool:
        raise ValueError('Invalid account scope')
    project = spec['project_path']
    if project is not None and not re.fullmatch(r'[\w.-]+(?:/[\w.-]+)+', project):
        raise ValueError('Invalid project path')
    if project is None and not spec['assigned_to_current_user']:
        raise ValueError('Global query needs an explicit assigned account')
    if type(q.get('user_id')) is not int or q['user_id'] <= 0:
        raise ValueError('Missing account identity')
    if project and (type(q.get('project_id')) is not int or q['project_id'] <= 0):
        raise ValueError('Missing project identity')
    if q['fields'] not in ({'count': 'integer'}, {'exists': 'string'}):
        raise ValueError('Unsupported answer fields')
    path = '/' + project + '/-/' + spec['kind'] if project else '/dashboard/' + spec['kind']
    params = {'scope': ['all'], 'state': [spec['state']]}
    if spec['assigned_to_current_user']:
        params['assignee_username'] = [spec['username']]
    u = urlsplit(q['reference_path'])
    if u.scheme or u.netloc or u.fragment or u.path != path or parse_qs(u.query, keep_blank_values=True) != params:
        raise ValueError('Reference URL does not express the complete query scope')


def values(q, count):
    if type(count) is not int or count < 0:
        raise ValueError('Invalid native collection count')
    return {'count': count} if 'count' in q['fields'] else {'exists': 'yes' if count else 'no'}


def reference(site, q):
    validate(q)
    spec = q['collection']
    state = list_reference(site, spec)
    if state['user_id'] != q['user_id'] or (spec['project_path'] and state['project']['id'] != q['project_id']):
        raise ValueError('Native collection identity changed')
    status = {'opened': 1, 'closed': 2, 'merged': 3}.get(spec['state'])
    count = sum(spec['state'] == 'all' or row['state_id'] == status for row in state['rows'])
    return {'object_id': 'gitlab-issuable-count:' + reference_fingerprint(spec),
            'values': values(q, count), 'source_state': state}


def observed_values(q, state, url):
    validate(q)
    actual, target = urlsplit(url), urlsplit(q['reference_path'])
    if actual.path != target.path or parse_qs(actual.query, keep_blank_values=True) != parse_qs(target.query):
        raise ValueError('Rendered collection URL/filter mismatch')
    spec = q['collection']
    if state.get('user_id') != q['user_id'] or state.get('needs_filter'):
        raise ValueError('Wrong account or missing query filter')
    if spec['project_path'] and state.get('project_ids') != [str(q['project_id'])]:
        raise ValueError('Wrong rendered project identity')
    label = {'opened': 'Open', 'closed': 'Closed', 'merged': 'Merged', 'all': 'All'}[spec['state']]
    active = [r['text'] for r in state['tabs'] if r['active']]
    if not state['tabs']:
        onboarding = state.get('issue_onboarding' if spec['kind'] == 'issues' else 'merge_request_onboarding')
        if not spec['project_path'] or not onboarding or state['items']:
            raise ValueError('No native counter or verified empty project')
        return values(q, 0)
    if len(active) != 1 or not re.fullmatch(re.escape(label) + r'\s+[\d,]+', active[0]):
        raise ValueError('Native status count missing or not active')
    count = int(re.sub(r'\D', '', active[0]))
    if count == 0 and (state['items'] or not (state.get('no_results') or
                        spec['kind'] == 'merge_requests' and state.get('merge_request_onboarding'))):
        raise ValueError('Empty count lacks an explicit native empty result')
    if count and not state['items']:
        raise ValueError('Count loaded but collection entries missing')
    prefix = '/' + spec['project_path'] + '/-/' + spec['kind'] + '/' if spec['project_path'] else None
    if prefix and any(not r['path'].startswith(prefix) for r in state['items']):
        raise ValueError('List contains another project')
    return values(q, count)


def ui_values(page, q):
    validate(q)
    # Native counters populate asynchronously; stop as soon as they appear.
    page.wait_for_function(r'''() => [...document.querySelectorAll('a.nav-link.active')]
      .some(e => e.getClientRects().length && /^(Open|Closed|Merged|All)\s+[\d,]+$/.test(e.innerText.trim())) ||
      document.body.innerText.includes('Use issues to collaborate on ideas, solve problems, and plan work') ||
      document.body.innerText.includes("Merge requests are a place to propose changes you've made to a project and discuss those changes with others")''', timeout=15000)
    return observed_values(q, read_issuable_list(page), page.url)
