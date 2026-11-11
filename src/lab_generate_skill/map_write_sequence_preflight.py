"""Tiny real PostgreSQL 11 allocator tests before any large website restore."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from .map_write_sequences import calibrate,TABLES
from .io_utils import atomic_write_json


def run(root,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    began=time.monotonic();server=None;cases=[]
    with tempfile.TemporaryDirectory(prefix='map-allocator-check-',dir=os.environ['TMPDIR']) as tmp:
      state=Path(tmp);(state/'run').mkdir();(state/'tmp').mkdir()
      base=['apptainer','exec','--cleanenv','--containall','--no-home','--no-mount','bind-paths,hostfs,cwd',
            '--bind',str(state)+':/state','--bind',str(state/'tmp')+':/tmp','--pwd','/state',
            str(Path(root)/'containers/webarena/map/db.sif')]
      pg='/usr/lib/postgresql/11/bin/'
      with (output/'postgres.log').open('w') as log:
       try:
        subprocess.run(base+[pg+'initdb','-D','/state/pg','-U','openstreetmap','-A','trust','--no-locale'],stdout=log,stderr=log,check=True,timeout=60)
        server=subprocess.Popen(base+[pg+'postgres','-D','/state/pg','-c','listen_addresses=','-c','unix_socket_directories=/state/run'],stdout=log,stderr=log,start_new_session=True)
        for _ in range(40):
            p=subprocess.run(base+[pg+'pg_isready','-h','/state/run','-U','openstreetmap','-d','postgres'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
            if p.returncode==0:break
            if server.poll()is not None:raise RuntimeError('Native test database exited')
            time.sleep(.25)
        else:raise RuntimeError('Native test database not ready')
        def sql(value):
            return subprocess.run(base+[pg+'psql','-XAt','-v','ON_ERROR_STOP=1','-h','/state/run','-U','openstreetmap','-d','postgres'],input="SET statement_timeout='10s';\n"+value,text=True,capture_output=True,check=True,timeout=20).stdout.strip()
        for table in TABLES:sql('CREATE TABLE '+table+' (id bigserial PRIMARY KEY);')
        # Reproduce the false negative exactly: pg_sequences reports NULL
        # for an unused sequence, although its next value 1 is valid above 0.
        sql('INSERT INTO users(id) VALUES(0);')
        old=sql("SELECT json_build_object('max_id',(SELECT max(id) FROM users),'last_value',(SELECT last_value FROM pg_sequences WHERE sequencename='users_id_seq'));")
        observed=json.loads(old.splitlines()[-1]);assert observed==dict(max_id=0,last_value=None)
        for label,high,sequence,called,expected in [('empty',None,1,False,1),('sentinel',0,1,False,1),('large',10929886113,1,False,10929886114),('ahead',42,100,True,101),('ahead_uncalled',42,100,False,100),('equal_uncalled',42,42,False,43)]:
            sql('TRUNCATE '+','.join(TABLES)+' RESTART IDENTITY;')
            for table in TABLES:
                if high is not None:sql(f'INSERT INTO {table}(id) VALUES({high});')
                sql(f"SELECT setval(pg_get_serial_sequence('{table}','id'),{sequence},{str(called).lower()});")
            proof=calibrate(SimpleNamespace(app_sql=sql))
            for table in TABLES:
                actual=int(sql(f"SELECT nextval(pg_get_serial_sequence('{table}','id')); ").splitlines()[-1])
                assert actual==expected,(label,table,actual,expected)
            cases.append(dict(case=label,next_id=expected,tables=len(TABLES),proof=proof))
            atomic_write_json(output/'progress.json',dict(cases=cases,original_null_failure_reproduced=True))
       finally:
        if server is not None and server.poll()is None:
            os.killpg(server.pid,signal.SIGINT)
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(server.pid,signal.SIGKILL);server.wait(timeout=5)
    result=dict(passed=True,cases=cases,original_null_failure_reproduced=True,seconds=time.monotonic()-began,large_database_restored=False)
    atomic_write_json(output/'result.json',result)
    return result
