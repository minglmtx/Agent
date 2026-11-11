"""Tiny native PostgreSQL audit validation, before a costly editor-site restore.

The temporary tables deliberately exercise only numeric identity tracking. Full
website state protection, ordinary browser writes and reset remain separate
acceptance requirements. No geographic data is loaded by this check.
"""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from .map_node_write_audit import TABLES,INSTALL_SQL,STATE_SQL,validate
from .io_utils import atomic_write_json


def exercise(sql):
    """Run against a fresh private native database, never a website database."""
    for table,(_,column) in TABLES.items():
        sql('CREATE TABLE public.'+table+' ('+column+' bigint NOT NULL, payload text);')
    sql(INSTALL_SQL);cases=[]
    def check(label,commands,*,ids=None,changesets=None,rejected=False):
        # One psql session per case, so rollback includes both public changes
        # and their audit rows. No clearing or suppression of an existing log.
        raw=sql('BEGIN;\n'+commands+'\n'+STATE_SQL+'\nROLLBACK;')
        state=json.loads(raw.splitlines()[-1])
        if rejected:
            try:validate(state)
            except ValueError:pass
            else:raise AssertionError('Invalid audit accepted: '+label)
        else:
            validate(state)
            assert state['node_ids']==(ids or []),(label,state)
            assert state['changeset_ids']==(changesets or []),(label,state)
        clean=validate(json.loads(sql(STATE_SQL).splitlines()[-1]))
        assert clean['node_ids']==[] and clean['changeset_ids']==[] and clean['truncated']==[]
        cases.append(dict(case=label,expected_rejection=rejected,rollback_verified=True))
    for table,(kind,column) in TABLES.items():
        commands=f"INSERT INTO {table} VALUES(1,'before'); UPDATE {table} SET {column}=10929886115,payload='after'; DELETE FROM {table};"
        check('old_new_deleted_identity:'+table,commands,
              ids=[1,10929886115]if kind=='node'else[],
              changesets=[1,10929886115]if kind=='changeset'else[])
    check('duplicate_writes_one_identity',"INSERT INTO current_nodes VALUES(3,'one'); UPDATE current_nodes SET payload='two'; UPDATE current_nodes SET payload='three';",ids=[3])
    check('savepoint_rollback_not_persisted',"SAVEPOINT discarded; INSERT INTO current_nodes VALUES(5,'discarded'); ROLLBACK TO discarded;")
    check('bounded_node_overflow',"INSERT INTO current_nodes SELECT generate_series(1,65),'too many';",rejected=True)
    check('bounded_changeset_overflow',"INSERT INTO changesets SELECT generate_series(1,65),'too many';",rejected=True)
    for table in TABLES:
        check('truncate_detected:'+table,'TRUNCATE public.'+table+';',rejected=True)
        check('disabled_row_trigger:'+table,'ALTER TABLE public.'+table+' DISABLE TRIGGER codex_node_audit_row;',rejected=True)
        check('disabled_truncate_trigger:'+table,'ALTER TABLE public.'+table+' DISABLE TRIGGER codex_node_audit_truncate;',rejected=True)
    return cases


def run(root,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    began=time.monotonic();server=None
    with tempfile.TemporaryDirectory(prefix='map-node-audit-check-',dir=os.environ['TMPDIR'])as tmp:
      state=Path(tmp);(state/'run').mkdir();(state/'tmp').mkdir()
      base=['apptainer','exec','--cleanenv','--containall','--no-home','--no-mount','bind-paths,hostfs,cwd',
            '--bind',str(state)+':/state','--bind',str(state/'tmp')+':/tmp','--pwd','/state',
            str(Path(root)/'containers/webarena/map/db.sif')]
      pg='/usr/lib/postgresql/11/bin/'
      with (output/'postgres.log').open('w')as log:
       try:
        subprocess.run(base+[pg+'initdb','-D','/state/pg','-U','openstreetmap','-A','trust','--no-locale'],stdout=log,stderr=log,check=True,timeout=60)
        server=subprocess.Popen(base+[pg+'postgres','-D','/state/pg','-c','listen_addresses=','-c','unix_socket_directories=/state/run'],stdout=log,stderr=log,start_new_session=True)
        for _ in range(40):
            p=subprocess.run(base+[pg+'pg_isready','-h','/state/run','-U','openstreetmap','-d','postgres'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
            if p.returncode==0:break
            if server.poll()is not None:raise RuntimeError('Native audit database exited')
            time.sleep(.25)
        else:raise RuntimeError('Native audit database not ready')
        def sql(value):
            return subprocess.run(base+[pg+'psql','-XqAt','-v','ON_ERROR_STOP=1','-h','/state/run','-U','openstreetmap','-d','postgres'],input="SET statement_timeout='10s';\n"+value,text=True,capture_output=True,check=True,timeout=20).stdout.strip()
        cases=exercise(sql)
       finally:
        if server is not None and server.poll()is None:
            os.killpg(server.pid,signal.SIGINT)
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(server.pid,signal.SIGKILL);server.wait(timeout=5)
    result=dict(passed=True,cases=cases,seconds=time.monotonic()-began,
                native_database='PostgreSQL 11',large_database_restored=False,
                website_reset_verified=False,training_admissions=0)
    atomic_write_json(output/'result.json',result)
    return result
