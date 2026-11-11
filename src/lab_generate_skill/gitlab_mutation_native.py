"""Private bounded native collectors; no mutation, inference or actor tools."""
import hashlib
import re
import subprocess
from .site_database import select_rows
from .gitlab_read_session import GitlabReadSession
from .gitlab_native_csv_probe import protected_snapshot, AUTH_COLUMNS


def git(site, ident, *args):
    if type(ident) is not int or ident <= 0:
        raise ValueError('Native project identity required')
    h = hashlib.sha256(str(ident).encode()).hexdigest()
    path = '/var/opt/gitlab/git-data/repositories/@hashed/'+h[:2]+'/'+h[2:4]+'/'+h+'.git'
    return site.command(['/opt/gitlab/embedded/bin/git', '--git-dir='+path, *args],
                        capture_output=True, timeout=45).stdout


def repository(site, ident, path, *, initial_head=None):
    head = git(site, ident, 'rev-parse', 'HEAD').decode().strip()
    branch = git(site, ident, 'symbolic-ref', '--short', 'HEAD').decode().strip()
    refs = {}
    for line in git(site, ident, 'for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads', 'refs/tags').decode().splitlines():
        name, value = line.split(' '); refs[name] = value
    files = {}
    for row in git(site, ident, 'ls-tree', '-r', '-z', head).split(b'\0'):
        if not row: continue
        info, name = row.split(b'\t', 1); mode, kind, oid = info.decode().split(' ')
        files[name.decode()] = {'mode': mode, 'oid': oid}
    contents = git(site, ident, 'show', head+':'+path) if path in files and files[path]['mode']=='100644' else None
    ancestor = None
    if initial_head:
        try:
            git(site, ident, 'merge-base', '--is-ancestor', initial_head, head); ancestor = True
        except subprocess.CalledProcessError as error:
            if error.returncode != 1: raise
            ancestor = False
    return {'identity': ident, 'head': head, 'branch': branch, 'refs': refs, 'files': files,
            'content_sha256': hashlib.sha256(contents).hexdigest() if contents is not None else None,
            'initial_head_is_ancestor': ancestor}


def notification_rows(rows, identity):
    """Preserve native PKs for unrelated rows, including duplicate global tuples.

    Only the exactly bound project/account uses a stable synthetic identity so
    a missing inherited setting and its later inserted row can be compared.
    Duplicate settings for that target are ambiguous and must fail closed.
    """
    output=[];target_count=0;seen=set()
    for row in rows:
        row=dict(row);pk=row['id']
        if type(pk) is not int or pk<=0 or pk in seen:
            raise ValueError('Unique native notification primary keys required')
        seen.add(pk)
        key=f"{row['source_type']}:{row['source_id']}:{row['user_id']}"
        if key==identity:
            row['id']=identity;target_count+=1
        else:
            row['id']='native:'+str(pk)
        output.append(row)
    if target_count>1:raise ValueError('Duplicate bound project notification settings')
    return output


def resolve_repository_path(files, declared):
    """Resolve an unqualified filename only when native tree has one match."""
    if declared in files:return declared
    if '/' in declared:raise ValueError('Declared repository path is absent')
    matches=[p for p in files if p.rsplit('/',1)[-1]==declared]
    if len(matches)!=1:raise ValueError('Repository filename missing or ambiguous')
    return matches[0]


def database(site, kind, identity):
    if kind == 'profile_name':
        rows = select_rows(site, 'SELECT id,username,name FROM users ORDER BY id')
    elif kind == 'visibility':
        rows = select_rows(site, 'SELECT id,name,path,namespace_id,visibility_level FROM projects ORDER BY id')
    elif kind == 'notifications':
        rows = select_rows(site, 'SELECT id,user_id,source_type,source_id,level FROM notification_settings ORDER BY id')
        rows = notification_rows(rows, identity)
        if not any(r['id'] == identity for r in rows):
            source, project, user = identity.split(':')
            rows.append({'id': identity, 'source_type': source, 'source_id': int(project), 'user_id': int(user), 'level': None})
        rows.sort(key=lambda r:r['id'])
    else: raise ValueError('Unsupported native database mutation')
    return {'identity': identity, 'rows': rows}


def protection(site, spec, account_id, progress):
    """Complete 16-table guard, masking only declared target fields.

    Native sign-in/activity metadata for this single account is not task state.
    This is a bounded capability guard; it does not claim all GitLab background
    queues, every repository, or every table were validated for RL admission.
    """
    if type(account_id) is not int or account_id <= 0:
        raise ValueError('Native account binding required')
    relation=None
    if spec['kind']=='visibility':
        from gitlab_visibility_native_read import read as read_visibility
        reader=getattr(site,'_visibility_reference_session',None)
        relation=(reader.project(site,spec['identity']) if reader is not None
                  else read_visibility(site,spec['identity']))
        if relation['project_id']!=spec['identity'] or relation['project_namespace_id']!=relation['namespace_id'] or relation['namespace_type']!='Project':
            raise ValueError('Exact native project namespace binding missing')
        if type(relation['namespace_id'])is not int or relation['namespace_id']<=0:raise ValueError('Invalid native namespace')
    with GitlabReadSession(site) as session:
        def reader(current, sql):
            expression = 'row_to_json(t)::text'
            if 'md5('+expression+')' in sql:
                if ' FROM "users" t' in sql:
                    fields = list(AUTH_COLUMNS) + (['name'] if spec['kind']=='profile_name' else [])
                    subtract = ''.join("-'"+f+"'" for f in fields)
                    sql=sql.replace(expression, f"(CASE WHEN t.id={account_id} THEN to_jsonb(t){subtract} ELSE to_jsonb(t) END)::text")
                elif ' FROM "projects" t' in sql and spec['kind'] in ('visibility','repository_file'):
                    ident=spec['identity']
                    if type(ident) is not int or ident<=0:raise ValueError('Native target project required')
                    fields=['updated_at','last_activity_at']+(['visibility_level','lfs_enabled','emails_disabled'] if spec['kind']=='visibility' else [])
                    subtract=''.join("-'"+f+"'" for f in fields)
                    sql=sql.replace(expression,f"(CASE WHEN t.id={ident} THEN to_jsonb(t){subtract} ELSE to_jsonb(t) END)::text")
                elif ' FROM "namespaces" t' in sql and relation is not None:
                    ident=relation['namespace_id']
                    sql=sql.replace(expression,f"(CASE WHEN t.id={ident} THEN to_jsonb(t)-'visibility_level'-'updated_at' ELSE to_jsonb(t) END)::text")
            return session.select_rows(current,sql)
        value=protected_snapshot(site,progress,reader=reader)
        if spec['kind']=='profile_name':
            value['profile_relations']={table:session.select_rows(site,'SELECT row_to_json(t) AS row FROM '+table+' t ORDER BY id') for table in ('namespaces','routes')}
        if relation is not None:value['visibility_relation']=relation
        return value


def watch_enum(site):
    raw=site.command(['cat','/opt/gitlab/embedded/service/gitlab-rails/app/models/notification_setting.rb'],
                     capture_output=True,text=True,timeout=20).stdout
    # Bind the native constant from this exact installed implementation.
    matches=re.findall(r'\bwatch:\s*(\d+)',raw)
    if len(matches)!=1:raise ValueError('Native notification watch enum unavailable or ambiguous')
    return int(matches[0])


def protection_equal(before,after,spec,account_id):
    if spec['kind']=='visibility':
        from .gitlab_visibility_effects import visibility_effects_equal
        return ({k:v for k,v in before.items() if k!='visibility_relation'}=={k:v for k,v in after.items() if k!='visibility_relation'}
            and visibility_effects_equal(before.get('visibility_relation'),after.get('visibility_relation'),spec))
    if spec['kind']!='profile_name':return before==after
    # Preserve complete snapshots. Permit only the native personal namespace
    # and its exact route to propagate the submitted profile display name.
    tables={'namespaces','routes','profile_relations'}
    if {k:v for k,v in before.items() if k not in tables}!={k:v for k,v in after.items() if k not in tables}:return False
    try:
        old={t:{r['row']['id']:r['row'] for r in before['profile_relations'][t]} for t in ('namespaces','routes')}
        new={t:{r['row']['id']:r['row'] for r in after['profile_relations'][t]} for t in ('namespaces','routes')}
        candidates=[r for r in old['namespaces'].values() if r.get('owner_id')==account_id and r.get('type') in (None,'User','UserNamespace','Namespaces::UserNamespace') and r.get('parent_id') is None]
        if len(candidates)!=1:return False
        namespace=candidates[0]['id']
        route_ids=[r['id'] for r in old['routes'].values() if r.get('source_type')=='Namespace' and r.get('source_id')==namespace]
        if len(route_ids)!=1:return False
        for table,target in [('namespaces',namespace),('routes',route_ids[0])]:
            if set(old[table])!=set(new[table]):return False
            for ident,row in old[table].items():
                final=new[table][ident]
                expected_name=None
                if ident==target:expected_name=spec['value']
                elif table=='routes' and row.get('source_type')=='Project':
                    child=old['namespaces'].get(row.get('namespace_id'),{})
                    if child.get('parent_id')==namespace and child.get('type')=='Project' and child.get('name') and row.get('path')==candidates[0]['path']+'/'+child.get('path',''):
                        if row.get('name')!=candidates[0]['name']+' / '+child['name']:return False
                        expected_name=spec['value']+' / '+child['name']
                if expected_name is None:
                    if row!=final:return False
                else:
                    if final.get('name')!=expected_name:return False
                    if {k:v for k,v in row.items() if k not in ('name','updated_at')}!={k:v for k,v in final.items() if k not in ('name','updated_at')}:return False
        return True
    except (KeyError,TypeError):return False
