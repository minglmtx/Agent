"""Terminal identity for an explicitly free-choice pending to-do target.

This checks target membership and rendered identity, not the navigation route.
Bindings requiring a particular click path need separate navigation evidence.
Native references are evaluator-private and must be rechecked before/after use.
"""
from urllib.parse import urlsplit, unquote
from .gitlab_todo_rules import todo_state, display_text
from .gitlab_directory import project_reference
from .gitlab_section import read_section


def target_paths(state, projects):
    targets = {}
    by_id = {r['id']: r for r in projects}
    for item in state['items']:
        if item['state'] != 'pending':
            continue
        p = by_id[item['project_id']]
        if p['path'] != item['project_path']:
            raise ValueError('To-do project reference mismatch')
        path = '/' + p['path']
        targets[path] = {'kind': 'project', 'project_id': p['id'], 'title': p['name']}
        if item['target_type'] == 'MergeRequest':
            targets[path + '/-/merge_requests/' + str(item['iid'])] = {
                'kind': 'merge_request', 'project_id': p['id'], 'iid': item['iid'],
                'id': item['target_id'], 'title': item['title']}
    if not targets:
        raise ValueError('No pending to-do targets')
    return targets


def validate(spec):
    if not isinstance(spec, dict) or spec.get('kind') not in ('project', 'merge_request'):
        raise ValueError('Explicit pending target kind required')
    if not isinstance(spec.get('username'), str) or not spec['username'] or type(spec.get('user_id')) is not int or spec['user_id'] <= 0:
        raise ValueError('Native account identity required')
    targets = spec.get('targets')
    if not isinstance(targets, dict) or not targets:
        raise ValueError('Complete pending target set required')
    for path, ref in targets.items():
        u = urlsplit(path)
        if not path.startswith('/') or path.startswith('//') or u.query or u.fragment or unquote(u.path) != path or path.endswith('/'):
            raise ValueError('Invalid target path')
        if ref.get('kind') != spec['kind'] or type(ref.get('project_id')) is not int or ref['project_id'] <= 0 or not isinstance(ref.get('title'), str) or not ref['title'].strip():
            raise ValueError('Invalid native target identity')
        if spec['kind'] == 'merge_request':
            if any(type(ref.get(k)) is not int or ref[k] <= 0 for k in ('id', 'iid')) or not path.endswith('/-/merge_requests/' + str(ref['iid'])):
                raise ValueError('Invalid native merge-request identity')
        elif '/-/' in path or len(path.strip('/').split('/')) < 2:
            raise ValueError('Invalid native project path')


def reference(site, username, kind):
    state = todo_state(site, username)
    targets = {path: ref for path, ref in target_paths(state, project_reference(site)).items() if ref['kind'] == kind}
    spec = {'username': username, 'user_id': state['user']['id'], 'kind': kind, 'targets': targets}
    validate(spec)
    return spec


def verify_reference(site, spec):
    validate(spec)
    if reference(site, spec['username'], spec['kind']) != spec:
        raise ValueError('Pending to-do target reference changed')


def read_target(page):
    return {'url': page.url, 'user_id': page.evaluate('() => window.gon?.current_user_id'),
            'headings': page.locator('h1:visible,h2:visible,h3:visible').all_inner_texts(),
            'section': read_section(page)}


def checks(spec, state):
    validate(spec)
    if not isinstance(state, dict) or not isinstance(state.get('url'), str) or not isinstance(state.get('headings'), list) or any(not isinstance(h, str) for h in state['headings']):
        raise ValueError('Missing native to-do target capture')
    section = state.get('section')
    if not isinstance(section, dict) or any(not isinstance(section.get(k), list) for k in ('project_ids', 'breadcrumbs', 'active_navigation')):
        raise ValueError('Missing native target section capture')
    u = urlsplit(state['url'])
    path = unquote(u.path).rstrip('/')
    ref = spec['targets'].get(path)
    result = {'todo_target_account': state.get('user_id') == spec['user_id'],
              'pending_todo_target': ref is not None and not u.query and not u.fragment,
              'todo_target_identity': False, 'todo_target_content': False}
    if ref is None:
        return result
    project = path.split('/-/merge_requests/')[0]
    crumbs = {r['path'].rstrip('/') for r in section['breadcrumbs']}
    active = {r['path'].rstrip('/') for r in section['active_navigation']}
    expected_page = 'projects:show' if spec['kind'] == 'project' else 'projects:merge_requests:show'
    sidebar = project if spec['kind'] == 'project' else project + '/-/merge_requests'
    result['todo_target_identity'] = (section['project_ids'] == [str(ref['project_id'])]
        and project in crumbs and path in crumbs and section.get('body_page') == expected_page
        and sidebar in active)
    result['todo_target_content'] = (section.get('main_id') == 'content-body'
        and display_text(ref['title']) in [display_text(h) for h in state['headings']])
    return result


FEEDBACK = {
    'todo_target_account': 'The page belongs to the requested signed-in account.',
    'pending_todo_target': 'The displayed object is an allowed target of the initial pending to-do list.',
    'todo_target_identity': 'The native project and object identity match the displayed target.',
    'todo_target_content': 'The target details and their title are actually rendered.'}
