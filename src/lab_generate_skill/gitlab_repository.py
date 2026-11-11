"""Native repository-view evidence, independent of the actor and target URL.

Private Git object references are never added to actor observations. The browser
reader consumes rendered controls/content only and never navigates or clicks.
"""
import hashlib
import re
from urllib.parse import urlsplit, unquote
from .gitlab_public_readiness import BLOB_SIGNALS


def content_digest(text):
    return hashlib.sha256(' '.join(text.split()).encode()).hexdigest()


def verify_repository_reference(site, spec):
    ident = spec['project_id']
    if type(ident) is not int or ident <= 0:
        raise ValueError('Invalid pinned project ID')
    digest = hashlib.sha256(str(ident).encode()).hexdigest()
    repo = '/var/opt/gitlab/git-data/repositories/@hashed/' + digest[:2] + '/' + digest[2:4] + '/' + digest + '.git'
    ref = spec['ref']
    if not re.fullmatch(r'[A-Za-z0-9_.][A-Za-z0-9_./-]*', ref) or '..' in ref:
        raise ValueError('Invalid pinned ref')
    def git(*args):
        return site.command(['/opt/gitlab/embedded/bin/git', '--git-dir='+repo, *args], capture_output=True, text=True, timeout=40).stdout.strip()
    if git('rev-parse', 'refs/heads/'+ref) != spec['head']:
        raise RuntimeError('Repository revision differs from pinned reference')
    if spec['kind'] in ('tree', 'blob'):
        path = spec['path']
        if path.startswith('/') or any(x in ('.','..') for x in path.split('/')):
            raise ValueError('Invalid repository path')
        target = 'refs/heads/'+ref+(':'+path if path else '^{tree}')
        if git('rev-parse', target) != spec['object_sha']:
            raise RuntimeError('Repository object differs from pinned reference')
    if spec.get('document_equivalence'):
        from .gitlab_document_equivalence import article_identity
        if spec['kind']!='blob' or article_identity(git('show','refs/heads/'+ref+':'+spec['path']))!=spec['document_equivalence']:
            raise RuntimeError('Article content reference differs from pinned Git object')
    return {'project_id': ident, 'head': spec['head'], 'object_sha': spec.get('object_sha')}


READ = r'''() => {
 const visible=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
 const links=sel=>[...document.querySelectorAll(sel)].filter(visible).map(e=>({text:e.innerText.trim(),href:e.getAttribute('href')}));
 return {
  project_ids:[...new Set([...document.querySelectorAll('[data-project-id]')].map(e=>e.getAttribute('data-project-id')))],
  tree_links:links('.tree-item a[href]'),
  raw_links:links('a[href*="/-/raw/"]'),
  commit_links:links('a[href*="/-/commit/"]'),
  tree_ref_links:links('a[href*="/-/tree/"]'),
  branch_links:links('a[data-qa-selector="branch_link"]'),
  content:[...document.querySelectorAll('.file-content')].filter(visible).map(e=>e.innerText),
  loading:[...document.querySelectorAll('.gl-spinner,[aria-busy="true"]')].some(visible) || ('''+BLOB_SIGNALS+r''')().length>0
 };
}'''

READY = r'''() => {
 const s = (''' + READ + r''')();
 if(s.loading) return false;
 const p=location.pathname;
 if(p.includes('/-/blob/')) return s.content.some(x=>x.trim());
 if(p.includes('/-/tree/')) return s.tree_links.some(x=>x.text && x.text!=='..');
 if(p.includes('/-/commits/')) return s.commit_links.length>0;
 if(p.includes('/-/branches')) return s.branch_links.length>0;
 if(!p.includes('/-/') && document.body.getAttribute('data-page')==='projects:show' && s.commit_links.length>0)
   return s.tree_links.some(x=>x.text && x.text!=='..' && /\/-\/(tree|blob)\//.test(x.href));
 if(document.querySelector('.tree-item')) return s.tree_links.some(x=>x.text && x.text!=='..');
 return true;
}'''


def read_repository_page(page):
    """Bounded wait only for the current native repository view to load."""
    from playwright.sync_api import TimeoutError
    wait_status = 'ready'
    # Error/login pages must not wait for repository controls.
    if '/-/' in urlsplit(page.url).path or page.locator('.tree-item,.file-content,body[data-page="projects:show"]').count():
        try:
            page.wait_for_function(READY, timeout=8000, polling=100)
        except TimeoutError:
            wait_status = 'content_wait_exhausted'
    from .document_sections import READ as section_reader
    from .gitlab_document_equivalence import READ_DIFFS
    # Vue navigation can change the document between separate evaluate calls.
    # Capture identity, body, sections and diffs within one browser JS turn.
    state = page.evaluate('''() => {
      const state = ('''+READ+''')();
      state.url = location.href;
      state.document_sections = ('''+section_reader+''')();
      if(location.pathname.includes('/-/commit/'))state.diff_files = ('''+READ_DIFFS+''')();
      return state;
    }''')
    state['wait_status'] = wait_status
    return state


def repository_checks(spec, state, current_url=None):
    if not isinstance(state, dict) or any(k not in state for k in
        ('project_ids','tree_links','raw_links','commit_links','tree_ref_links','content','loading','wait_status')):
        raise ValueError('Missing repository browser capture')
    if current_url is not None and 'url'in state and state['url']!=current_url:
        raise ValueError('Repository capture and terminal URL differ')
    if any(not isinstance(state[k],list) for k in ('project_ids','tree_links','raw_links','commit_links','tree_ref_links','content')):
        raise ValueError('Malformed repository browser capture')
    if type(state['loading']) is not bool or any(not isinstance(x,str) for x in state['content']):
        raise ValueError('Malformed repository content')
    def paths(name):
        out=[]
        for link in state[name]:
            if not isinstance(link,dict) or not isinstance(link.get('href'),str) or not isinstance(link.get('text'),str):
                raise ValueError('Malformed repository link capture')
            out.append((unquote(urlsplit(link['href']).path).rstrip('/'),link['text']))
        return out
    checks={'repository_identity':str(spec['project_id']) in state['project_ids'],
            'repository_content_loaded':not state['loading'] and state['wait_status']=='ready'}
    base='/'+spec['project'];ref=spec['ref'];kind=spec['kind']
    if spec.get('browse_subtree'):
        if not isinstance(current_url,str):raise ValueError('Subtree browsing requires a captured current URL')
        match=re.fullmatch(re.escape(base+'/-/')+r'(tree|blob)/'+re.escape(ref)+r'/(.+?)/?',unquote(urlsplit(current_url).path))
        selected=next((o for o in spec['browse_objects'] if match and o['kind']==match[1] and o['path']==match[2]),None)
        if not selected or not (selected['path']==spec['path'] or selected['path'].startswith(spec['path']+'/')):
            return {**checks,'repository_object_content':False}
        spec={**spec,**selected};kind=spec['kind']
    if kind=='tree':
        # Rows also contain last-commit links, which are not directory entries.
        actual={p for p,text in paths('tree_links') if text!='..' and ('/-/tree/' in p or '/-/blob/' in p)}
        expected=set(spec['child_paths'])
        if not expected:raise ValueError('Empty directory reference is not supported')
        # GitLab lazily renders long directories. Viewing a directory does not
        # require scrolling through every entry; every displayed entry must
        # nevertheless belong to the independently pinned directory.
        checks['repository_object_content']=bool(actual) and actual<=expected
    elif kind=='blob':
        raw=base+'/-/raw/'+ref+'/'+spec['path']
        native_file=raw in {p for p,_ in paths('raw_links')} and any(x.strip() for x in state['content'])
        # A README rendered on the project/tree page is the same readable
        # content. Its hash comes from an independently inspected file view.
        rendered=bool(spec.get('rendered_content_sha256')) and any(content_digest(x)==spec['rendered_content_sha256'] for x in state['content'])
        checks['repository_object_content']=native_file or rendered
    elif kind=='commits':
        commits={p.rsplit('/',1)[-1] for p,_ in paths('commit_links') if p.startswith(base+'/-/commit/')}
        checks['repository_object_content']=spec['head'] in commits and len(commits)>=spec['minimum_commits']
    elif kind=='branches':
        if not isinstance(state.get('branch_links'),list):raise ValueError('Missing native branch-list capture')
        actual={p for p,_ in paths('branch_links')}
        checks['repository_object_content']=bool(spec['branches']) and actual=={base+'/-/tree/'+branch for branch in spec['branches']}
    else:raise ValueError('Unsupported repository view')
    if spec.get('visible_section'):
        from .document_sections import section_checks
        if kind!='blob':raise ValueError('Section selection requires a pinned document')
        checks.update(section_checks(spec['visible_section'],state.get('document_sections'),
                                     issued_request=state.get('issued_section_request'),current_url=current_url))
    return checks
