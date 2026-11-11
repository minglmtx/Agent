"""Native project/section identity for terminal navigation evaluation."""
READ = r'''() => ({
 body_page:document.body.getAttribute('data-page'),
 project_ids:[...new Set([...document.querySelectorAll('[data-project-id]')].map(e=>e.getAttribute('data-project-id')))],
 breadcrumbs:[...document.querySelectorAll('.breadcrumbs a[href]')].map(e=>({text:e.innerText,path:new URL(e.href).pathname})),
 active_navigation:[...document.querySelectorAll('.nav-sidebar li.active > a[href],.nav-sidebar li.is-active > a[href]')].map(e=>({text:e.innerText,path:new URL(e.href).pathname})),
 main_id:document.querySelector('main')?.id||'',
 main_classes:document.querySelector('main')?.className||''
})'''


def read_section(page):
    return page.evaluate(READ)


def section_checks(spec, state):
    if not isinstance(state, dict) or not isinstance(state.get('body_page'), str):
        raise ValueError('Missing native project section capture')
    if any(not isinstance(state.get(k), list) for k in ('project_ids', 'breadcrumbs', 'active_navigation')):
        raise ValueError('Malformed native section identity')
    project = '/' + spec['project_path'].strip('/')
    target = spec['section_path'].rstrip('/')
    breadcrumbs = {r['path'].rstrip('/') for r in state['breadcrumbs']}
    active = {r['path'].rstrip('/') for r in state['active_navigation']}
    # Starrers is a native project-information page with no active sidebar
    # entry. Still require its project ID, exact body page and breadcrumb.
    sidebar_matches=(not active if spec['body_page']=='projects:starrers:index'
                     and target==project+'/-/starrers' else target in active)
    return {'section_project_identity': state['project_ids'] == [str(spec['project_id'])] and project in breadcrumbs,
            'native_section_identity': state['body_page'] == spec['body_page'],
            'native_section_breadcrumb': target in breadcrumbs,
            'native_section_active': sidebar_matches,
            'native_section_content': state.get('main_id') == 'content-body'}


FEEDBACK = {'section_project_identity': 'The loaded section belongs to the requested project.',
            'native_section_identity': 'The native page is the requested kind of project section.',
            'native_section_breadcrumb': 'The rendered breadcrumb identifies the requested section.',
            'native_section_active': 'The native sidebar state matches the requested section.',
            'native_section_content': 'The native section content container is present.'}
