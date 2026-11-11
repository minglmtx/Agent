"""Reuse the completed tiny PostgreSQL check, never website admission."""
import hashlib
import json
from pathlib import Path


def load(path, *, project):
    config=json.loads(Path(path).read_text())
    def read(pin):
        raw=Path(pin['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=pin['sha256']:
            raise ValueError('Native audit proof changed')
        return json.loads(raw)
    report=read(config['report']);members=read(config['runtime_members'])
    for name in ('map_node_write_audit','map_node_write_audit_preflight','io_utils'):
        relative='src/lab_generate_skill/'+name+'.py'
        if hashlib.sha256((Path(project)/relative).read_bytes()).hexdigest()!=members[relative]['sha256']:
            raise ValueError('Native audit implementation changed; revalidation required')
    result=report['write_audit_preflight']
    from .map_node_write_audit import TABLES
    expected={kind+':'+table for table in TABLES for kind in
              ('old_new_deleted_identity','truncate_detected','disabled_row_trigger','disabled_truncate_trigger')}
    expected.update(('duplicate_writes_one_identity','savepoint_rollback_not_persisted',
                     'bounded_node_overflow','bounded_changeset_overflow'))
    cases=result.get('cases',[])
    if (result.get('passed')is not True or result.get('native_database')!='PostgreSQL 11'
            or len(cases)!=len(expected) or {c['case']for c in cases}!=expected
            or any(c.get('rollback_verified')is not True for c in cases)):
        raise ValueError('Complete native audit and rollback proof required')
    return dict(result,reused=True,proof_config=str(path),website_reset_verified=False)
