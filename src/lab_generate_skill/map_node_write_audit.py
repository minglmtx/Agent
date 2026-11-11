"""Track touched native node IDs without scanning the geographic baseline.

This is observation, not rollback or permission enforcement. Original writes
still occur; the existing whole-site dirty guard still forces a clean rebuild.
Only numeric object IDs are retained, never credentials or full duplicate rows.
"""
import json
from .map_node_readout import MAX_NODES,integer

TABLES={'current_nodes':('node','id'),'current_node_tags':('node','node_id'),
        'nodes':('node','node_id'),'node_tags':('node','node_id'),
        'changesets':('changeset','id'),'changeset_tags':('changeset','changeset_id')}

INSTALL_SQL="""
CREATE SCHEMA codex_node_audit;
CREATE TABLE codex_node_audit.touched(kind text NOT NULL,id bigint NOT NULL,PRIMARY KEY(kind,id));
CREATE TABLE codex_node_audit.truncated(table_name text PRIMARY KEY);
CREATE FUNCTION codex_node_audit.record_row() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE object_id bigint;
BEGIN
 IF TG_OP IN ('UPDATE','DELETE') THEN
  object_id := (to_jsonb(OLD)->>TG_ARGV[1])::bigint;
  INSERT INTO codex_node_audit.touched VALUES(TG_ARGV[0],object_id) ON CONFLICT DO NOTHING;
 END IF;
 IF TG_OP IN ('UPDATE','INSERT') THEN
  object_id := (to_jsonb(NEW)->>TG_ARGV[1])::bigint;
  INSERT INTO codex_node_audit.touched VALUES(TG_ARGV[0],object_id) ON CONFLICT DO NOTHING;
 END IF;
 RETURN NULL;
END $$;
CREATE FUNCTION codex_node_audit.record_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO codex_node_audit.truncated VALUES(TG_TABLE_NAME) ON CONFLICT DO NOTHING;
 RETURN NULL;
END $$;
"""
for _table,(_kind,_column) in TABLES.items():
    INSTALL_SQL+=f"""
CREATE TRIGGER codex_node_audit_row AFTER INSERT OR UPDATE OR DELETE ON public.{_table}
 FOR EACH ROW EXECUTE PROCEDURE codex_node_audit.record_row('{_kind}','{_column}');
CREATE TRIGGER codex_node_audit_truncate AFTER TRUNCATE ON public.{_table}
 FOR EACH STATEMENT EXECUTE PROCEDURE codex_node_audit.record_truncate();
"""

STATE_SQL="""SELECT json_build_object(
 'row_tracked',(SELECT json_agg(c.relname ORDER BY c.relname) FROM pg_trigger t
 JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND t.tgname='codex_node_audit_row' AND t.tgenabled='O'
 AND t.tgfoid='codex_node_audit.record_row()'::regprocedure),
 'truncate_tracked',(SELECT json_agg(c.relname ORDER BY c.relname) FROM pg_trigger t
 JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND t.tgname='codex_node_audit_truncate' AND t.tgenabled='O'
 AND t.tgfoid='codex_node_audit.record_truncate()'::regprocedure),
 'truncated',(SELECT coalesce(json_agg(table_name ORDER BY table_name),'[]'::json) FROM codex_node_audit.truncated),
 'node_ids',(SELECT coalesce(json_agg(id ORDER BY id),'[]'::json) FROM
  (SELECT id FROM codex_node_audit.touched WHERE kind='node' ORDER BY id LIMIT 65) q),
 'changeset_ids',(SELECT coalesce(json_agg(id ORDER BY id),'[]'::json) FROM
  (SELECT id FROM codex_node_audit.touched WHERE kind='changeset' ORDER BY id LIMIT 65) q));"""


def validate(value):
    if not isinstance(value,dict) or set(value)!={'row_tracked','truncate_tracked','truncated','node_ids','changeset_ids'}:
        raise ValueError('Complete native row audit required')
    for key in ('row_tracked','truncate_tracked'):
        if value[key]!=sorted(TABLES):raise ValueError('Native write audit coverage changed')
    if value['truncated']!=[]:raise ValueError('Unbounded native object truncation needs diagnosis')
    for key in ('node_ids','changeset_ids'):
        ids=value[key]
        if not isinstance(ids,list)or len(ids)>MAX_NODES:raise ValueError('Native touched-object set exceeds bounded capture')
        for value_id in ids:integer(value_id,minimum=1)
        if ids!=sorted(set(ids)):raise ValueError('Native touched-object identities malformed')
    return value


def install(site):
    # Install only before an episode; do not reset or clear a dirty audit.
    site.reset_guard.require_unchanged()
    site.app_sql(INSTALL_SQL)
    initial=read(site)
    if initial['node_ids']or initial['changeset_ids']:
        raise ValueError('Node audit was dirty at installation')
    site.reset_guard.require_unchanged()
    return initial


def read(site):
    return validate(json.loads(site.app_sql(STATE_SQL)))
