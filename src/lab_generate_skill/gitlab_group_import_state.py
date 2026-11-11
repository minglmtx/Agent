"""Read-only native state capture for local group metadata import.

Exclude only the declared target's allowed new rows; all existing records and
all repositories remain protected. Login bookkeeping is normalized explicitly.
"""
import re
from .site_database import select_rows
from .gitlab_native_csv_probe import protected_snapshot,AUTH_COLUMNS,PROTECTED_TABLES
from .gitlab_read_session import GitlabReadSession
from .gitlab_persisted_goal_runtime import refs_snapshot


def group_projection(site, path):
    if not isinstance(path,str)or not re.fullmatch(r'[a-z][a-z0-9-]{0,100}',path):
        raise ValueError('Explicit top-level native group path required')
    rows=select_rows(site,"SELECT n.id,n.name,n.path,n.description,n.visibility_level FROM namespaces n JOIN routes r ON r.source_id=n.id AND r.source_type='Namespace' WHERE n.type='Group' AND n.parent_id IS NULL AND r.path='"+path+"'")
    if not rows:return None
    if len(rows)!=1:raise ValueError('Ambiguous native group identity')
    ident=rows[0]['id']
    if type(ident)is not int or ident<=0:raise ValueError('Native group key missing')
    labels=select_rows(site,f"SELECT title,color,description FROM labels WHERE group_id={ident} AND type='GroupLabel' ORDER BY title")
    milestones=select_rows(site,f'SELECT title,description,start_date,due_date FROM milestones WHERE group_id={ident} ORDER BY title')
    members=select_rows(site,f"SELECT u.username,m.access_level FROM members m JOIN users u ON u.id=m.user_id WHERE m.source_id={ident} AND m.source_type='Namespace' AND m.type='GroupMember' ORDER BY u.username")
    count=select_rows(site,f'SELECT count(*) AS count FROM projects WHERE namespace_id={ident}')[0]['count']
    states=select_rows(site,f'SELECT group_id,user_id,status,jid FROM group_import_states WHERE group_id={ident}')
    return dict(identity=rows[0],projection=dict(description=rows[0]['description'],
        labels=[[r[k]for k in ('title','color','description')]for r in labels],
        milestones=[[r[k]for k in ('title','description','start_date','due_date')]for r in milestones],
        members=[[r[k]for k in ('username','access_level')]for r in members],project_count=count),
        native_import_states=states)


def protection_query(sql, target_id):
    if target_id is not None and (type(target_id)is not int or target_id<=0):
        raise ValueError('Native positive target key required')
    match=re.search(r'FROM "([a-z_]+)"(?: t)?(?: |$)',sql)
    if not match:return sql
    table=match[1]
    if table not in PROTECTED_TABLES:raise ValueError('Undeclared protected table')
    if table=='users':
        auth=','.join("'"+n+"'"for n in AUTH_COLUMNS)
        sql=sql.replace('md5(row_to_json(t)::text)',f'md5((to_jsonb(t)-ARRAY[{auth}]::text[])::text)')
    if target_id is None:return sql
    filters={
        'namespaces':f'id <> {target_id}',
        'routes':f"(source_type IS DISTINCT FROM 'Namespace' OR source_id IS DISTINCT FROM {target_id})",
        'labels':f'group_id IS DISTINCT FROM {target_id}',
        'milestones':f'group_id IS DISTINCT FROM {target_id}',
        'members':f"(source_id IS DISTINCT FROM {target_id} OR source_type IS DISTINCT FROM 'Namespace' OR type IS DISTINCT FROM 'GroupMember')",
    }
    if table in filters:
        sql=f'SELECT * FROM (WITH "{table}" AS (SELECT * FROM public."{table}" WHERE {filters[table]}) '+sql+') AS protected_scope'
    return sql


def capture(site,path,*,progress=None,initial=None):
    target=group_projection(site,path)
    groups=select_rows(site,"SELECT id,md5(row_to_json(n)::text) AS md5 FROM namespaces n WHERE type='Group' ORDER BY id")
    added=({r['id'] for r in groups}-{r['id'] for r in initial['state']['groups']}) if initial is not None else set()
    # A wrong new group is a valid failed attempt, not a changed old object.
    # Protect all old rows while allowing this one candidate's new relations.
    ident=next(iter(added)) if len(added)==1 else None
    with GitlabReadSession(site)as session:
        def reader(site,sql):return session.select_rows(site,protection_query(sql,ident))
        tables=protected_snapshot(site,progress,reader=reader)
        extras={}
        for table,key in [('namespace_settings','namespace_id'),('group_import_states','group_id')]:
            where=f' WHERE {key} IS DISTINCT FROM {ident}' if ident is not None else ''
            extras[table]=session.select_rows(site,f'SELECT {key},md5(row_to_json(t)::text) AS md5 FROM {table} t'+where+f' ORDER BY {key}')
    refs=refs_snapshot(site)
    # Group identity projection and the full guard must describe the same saved
    # object; settlement/worker shutdown is the caller's responsibility.
    return dict(state=dict(groups=groups,project_fingerprint=tables['projects']['sha256'],target=target),
                guard=dict(tables=tables,extra_relations=extras,repositories=refs))
