"""Native Web IDE navigation identity; this does not claim edits were saved."""
from urllib.parse import urlsplit,unquote
import re


def validate(spec):
    if (not isinstance(spec,dict)or not isinstance(spec.get('project'),str)
        or not re.fullmatch(r'[\w.-]+(?:/[\w.-]+)+',spec['project'])
        or not isinstance(spec.get('ref'),str)or not spec['ref']
        or not isinstance(spec.get('root_entries'),list)or not spec['root_entries']
        or any(not isinstance(s,str)or not s or '/'in s for s in spec['root_entries'])):
        raise ValueError('Explicit pinned project, branch and native root entries required')


READ=r'''() => {
 const shown=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const es=s=>[...document.querySelectorAll(s)].filter(shown);
 return {url:location.href,
   project_links:es('.ide-context-header a[href]').map(e=>({href:e.href,text:e.innerText.trim()})),
   file_trees:es('.ide-tree-body').map(e=>e.innerText.trim()),
   editor_visible:es('.ide-view').length===1,
   edit_tab_visible:es('[data-qa-selector="edit_mode_tab"]').length===1,
   loading:es('.ide-view .gl-spinner,.ide-view [aria-busy="true"]').length>0};
}'''


def read_ide(page):return page.evaluate(READ)


def ide_checks(spec,state):
    validate(spec)
    if (not isinstance(state,dict)or not isinstance(state.get('url'),str)
        or any(type(state.get(k))is not bool for k in ('editor_visible','edit_tab_visible','loading'))
        or not isinstance(state.get('project_links'),list)or not isinstance(state.get('file_trees'),list)
        or any(not isinstance(t,str)for t in state['file_trees'])):
        raise ValueError('Missing native Web IDE capture')
    origin=urlsplit(state['url']);prefix='/-/ide/project/'+spec['project']+'/edit/'+spec['ref']
    path=unquote(origin.path).rstrip('/')
    # GitLab canonicalizes the repository root to /edit/<ref>/-/.
    # Removing its final slash must not turn a valid empty path into a failure.
    route=path in (prefix,prefix+'/-')or path.startswith(prefix+'/-/')
    matches=[]
    for r in state['project_links']:
        if not isinstance(r,dict)or any(not isinstance(r.get(k),str)for k in ('href','text')):
            raise ValueError('Malformed IDE project link')
        u=urlsplit(r['href'])
        if ((u.scheme,u.netloc)==(origin.scheme,origin.netloc)and unquote(u.path).rstrip('/')=='/'+spec['project']
            and not u.query and not u.fragment and spec['project']in r['text'].splitlines()):matches.append(r)
    lines={s.strip()for t in state['file_trees']for s in t.splitlines()}
    return {'ide_project_identity':route and len(matches)==1,
            'ide_interface_ready':state['editor_visible']and state['edit_tab_visible']and not state['loading'],
            'ide_repository_tree_loaded':len(state['file_trees'])==1 and bool(lines.intersection(spec['root_entries']))}


FEEDBACK={'ide_project_identity':'The native editor identifies the requested project and branch.',
          'ide_interface_ready':'The Web IDE and its edit interface are present and no longer loading.',
          'ide_repository_tree_loaded':'The native repository file tree is loaded in the editor.'}
