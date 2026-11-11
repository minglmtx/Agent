"""Observe native app writes; reuse only a provably untouched Map deployment.

This does not make the website read-only or intercept an actor action. Every
committed public-table write, sequence change, and persistent public/storage
file change forces a cold rebuild before another episode. Browser contexts are
always independent. Search/routing data are immutable query backends; tile
caches and Rails logs are not task state.
"""
import hashlib
import json


class MapStateChanged(RuntimeError):
    pass


INSTALL_SQL = """
CREATE SCHEMA codex_reset_guard;
CREATE TABLE codex_reset_guard.changed (table_name text PRIMARY KEY);
CREATE FUNCTION codex_reset_guard.record_write() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO codex_reset_guard.changed VALUES (TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME)
 ON CONFLICT DO NOTHING;
 RETURN NULL;
END $$;
DO $$ DECLARE r record; BEGIN
 FOR r IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p') LOOP
 EXECUTE format('CREATE TRIGGER codex_reset_guard_write AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON public.%I FOR EACH STATEMENT EXECUTE PROCEDURE codex_reset_guard.record_write()', r.relname);
 END LOOP;
END $$;
"""

STATE_SQL = """
SELECT json_build_object(
 'tables', (SELECT json_agg(relname ORDER BY relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p')),
 'tracked', (SELECT json_agg(c.relname ORDER BY c.relname) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND t.tgname='codex_reset_guard_write' AND t.tgenabled='O'),
 'changed', (SELECT coalesce(json_agg(table_name ORDER BY table_name),'[]'::json) FROM codex_reset_guard.changed),
 'sequences', (SELECT coalesce(json_agg(json_build_array(sequencename,last_value) ORDER BY sequencename),'[]'::json) FROM pg_sequences WHERE schemaname='public')
);
"""


def checked_state(state):
    if not isinstance(state, dict) or not state.get('tables') or state.get('tables') != state.get('tracked'):
        raise RuntimeError('Map write guard does not cover every public table')
    if not isinstance(state.get('changed'), list) or not isinstance(state.get('sequences'), list):
        raise RuntimeError('Map write guard returned incomplete state')
    return state


def persistent_files(app):
    rows = []
    for directory in ('storage', 'public'):
        for path in sorted((app/directory).rglob('*')):
            if path.is_symlink():
                raise RuntimeError('Untracked symbolic link in persistent Map files: '+str(path))
            if path.is_file():
                rows.append((str(path.relative_to(app)), hashlib.sha256(path.read_bytes()).hexdigest()))
    return rows


class MapResetGuard:
    def __init__(self, site):
        self.site = site
        site.app_sql(INSTALL_SQL)
        self.initial = self.fingerprint()

    def fingerprint(self):
        state = checked_state(json.loads(self.site.app_sql(STATE_SQL)))
        payload = {'baseline': self.site.geographic_baseline, 'database': state,
                   'files': persistent_files(self.site.state/'frontend/app')}
        if getattr(self.site,'community_fixture',None) is not None:
            payload['community_fixture']=self.site.community_fixture
        if getattr(self.site,'native_provider_binding',None) is not None:
            payload['native_provider_environment']=self.site.native_provider_binding
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def require_unchanged(self):
        if self.fingerprint() != self.initial:
            raise MapStateChanged('Map persistent state changed; cold deployment required')
