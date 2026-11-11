"""Exact immediate directory names: pinned Git reference versus native tree UI."""
import hashlib,re
from urllib.parse import urlsplit,urljoin,unquote
from .site_database import select_rows
from .gitlab_repository import read_repository_page


def validate(q):
    if q.get('fields')!={'directories':'record_set'}or q.get('record_fields')!={'directories':{'name':'string'}}:
        raise ValueError('Directory query requires a typed name set')
    if type(q.get('object_id'))is not int or q['object_id']<=0:raise ValueError('Invalid project identity')
    for key in ('head','object_sha'):
        if not re.fullmatch('[0-9a-f]{40}',q.get(key,'')):raise ValueError('Pinned tree reference missing')
    for key in ('project','ref','tree_path'):
        value=q.get(key)
        if not isinstance(value,str)or not value or value.startswith('/')or any(s in ('','.','..')for s in value.split('/'))or any(c in value for c in ('\x00','\n',':')):
            raise ValueError('Invalid tree identity')
    if q.get('reference_path')!='/'+q['project']+'/-/tree/'+q['ref']+'/'+q['tree_path']:
        raise ValueError('Tree reference URL differs')


def directory_records(raw):
    names=[]
    for row in raw.split('\0'):
        if not row:continue
        match=re.fullmatch(r'([0-7]{6}) (tree|blob|commit) ([0-9a-f]{40})\t([^/\0]+)',row)
        if not match:raise ValueError('Malformed native Git tree entry')
        if match[2]=='tree':names.append(match[4])
    if len(set(names))!=len(names):raise ValueError('Duplicate directory name')
    return {'directories':[{'name':s}for s in sorted(names)]}


def reference(site,q):
    validate(q);ident=q['object_id']
    rows=select_rows(site,f"SELECT r.path FROM routes r WHERE r.source_type='Project' AND r.source_id={ident}")
    if len(rows)!=1 or rows[0]['path']!=q['project']:raise ValueError('Project identity changed')
    sha=hashlib.sha256(str(ident).encode()).hexdigest()
    repo='/var/opt/gitlab/git-data/repositories/@hashed/'+sha[:2]+'/'+sha[2:4]+'/'+sha+'.git'
    def git(*args):
        r=site.command(['/opt/gitlab/embedded/bin/git','--git-dir='+repo,*args],capture_output=True,text=True,timeout=40)
        if r.returncode:raise RuntimeError('Private Git tree read failed')
        return r.stdout
    if git('rev-parse','refs/heads/'+q['ref']).strip()!=q['head']:raise ValueError('Branch differs from pinned commit')
    tree=q['head']+':'+q['tree_path']
    if git('rev-parse',tree).strip()!=q['object_sha']or git('cat-file','-t',tree).strip()!='tree':
        raise ValueError('Directory differs from pinned tree object')
    values=directory_records(git('ls-tree','-z',tree))
    return {'object_id':'gitlab_tree:'+str(ident)+':'+q['tree_path'],'values':values,
            'evidence':{'head':q['head'],'object_sha':q['object_sha']}}


def values_from_state(q,state,url):
    validate(q);origin=urlsplit(url)
    if unquote(origin.path).rstrip('/')!=q['reference_path']or origin.query or origin.fragment:
        raise ValueError('Wrong directory page')
    if state.get('wait_status')!='ready'or state.get('loading')or str(q['object_id'])not in state.get('project_ids',[]):
        raise ValueError('Native directory identity or readiness missing')
    prefix='/'+q['project']+'/-/tree/'+q['ref']+'/'+q['tree_path']+'/'
    names=[]
    for row in state.get('tree_links',[]):
        if row.get('text')=='..':continue
        u=urlsplit(urljoin(url,row['href']));path=unquote(u.path)
        if '/-/tree/'not in path:continue
        if (u.scheme,u.netloc)!=(origin.scheme,origin.netloc)or not path.startswith(prefix)or u.query or u.fragment:
            raise ValueError('Wrong branch or foreign directory entry')
        name=path[len(prefix):]
        # A collapsed multi-level directory needs explicit handling; never
        # silently rename it or return descendant paths as immediate children.
        if not name or '/'in name or row['text']!=name:raise ValueError('Ambiguous or collapsed directory label')
        names.append(name)
    if len(names)!=len(set(names)):raise ValueError('Duplicate native directory entry')
    # Admission independently compares this set to the full Git tree. A
    # partially rendered list cannot be admitted as a complete answer.
    return {'directories':[{'name':s}for s in sorted(names)]}


def ui_values(page,q):
    return values_from_state(q,read_repository_page(page),page.url)
