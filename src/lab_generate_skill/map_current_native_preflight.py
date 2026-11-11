"""Tiny real PostgreSQL check before restoring a large native Map checkpoint."""
import io
import json
from pathlib import Path
import signal
import subprocess
import time

from .map_current_resume import dependency_levels, resume_table
from .pg_stream_session import PsqlSession
from .map_sequence_finalize import sequence_sql


def run(base, state, output):
    """Use a separate disposable cluster, with actual parent/child foreign keys."""
    state = Path(state); output = Path(output)
    probe = state/'probe'; probe.mkdir(mode=0o700)
    (probe/'run').mkdir(mode=0o700)
    bin_path = '/usr/lib/postgresql/11/bin/'
    began = time.monotonic(); server = None
    log = (output/'native-preflight-postgres.log').open('w')
    try:
        subprocess.run(base+[bin_path+'initdb', '-D', '/state/probe/pg', '-U', 'openstreetmap',
            '-A', 'trust', '--no-locale'], stdout=log, stderr=log, check=True, timeout=60)
        server = subprocess.Popen(base+[bin_path+'postgres', '-D', '/state/probe/pg',
            '-c', 'listen_addresses=', '-c', 'unix_socket_directories=/state/probe/run'],
            stdout=log, stderr=log, start_new_session=True)
        ready = False
        for _ in range(40):
            p = subprocess.run(base+[bin_path+'pg_isready', '-h', '/state/probe/run',
                '-U', 'openstreetmap', '-d', 'postgres'], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=5)
            if p.returncode == 0: ready = True; break
            if server.poll() is not None: break
            time.sleep(.25)
        if not ready: raise RuntimeError('Native preflight PostgreSQL did not start')
        command = base+[bin_path+'psql','-XAtq','-h','/state/probe/run', '-U','openstreetmap',
                        '-d','postgres','-v','ON_ERROR_STOP=1']
        with PsqlSession(command, output/'native-preflight-sql.log') as session:
            session.query("SET statement_timeout='10s'; SET lock_timeout='2s';")
            session.query('CREATE TABLE users(id bigserial PRIMARY KEY);')
            sequence_cases = []
            for existing, expected_next in [(None, 1), (0, 1), (42, 43)]:
                session.query('TRUNCATE users RESTART IDENTITY;')
                if existing is not None:
                    session.query(f'INSERT INTO users(id) VALUES ({existing});')
                if existing == 0:
                    old_sequence = subprocess.run(command+['-c',
                        "SELECT setval(pg_get_serial_sequence('users','id'),"
                        "COALESCE((SELECT max(id) FROM users),1),EXISTS(SELECT 1 FROM users));"],
                        capture_output=True,text=True,timeout=15)
                    if old_sequence.returncode == 0 or 'out of bounds' not in old_sequence.stderr:
                        raise ValueError('Original sentinel sequence failure not reproduced')
                session.query(sequence_sql('users'))
                actual = int(session.query("SELECT nextval(pg_get_serial_sequence('users','id'));"))
                if actual != expected_next:
                    raise ValueError('Sequence initialization skipped or reused a real ID')
                sequence_cases.append(dict(existing_id=existing, next_id=actual))
            session.query('''CREATE TABLE relations(relation_id bigint PRIMARY KEY,
                changeset_id bigint, timestamp timestamp, visible boolean, version bigint);
                CREATE TABLE current_relations(id bigint PRIMARY KEY, changeset_id bigint,
                timestamp timestamp, visible boolean, version bigint);
                CREATE TABLE relation_tags(relation_id bigint,k text,v text,PRIMARY KEY(relation_id,k));
                CREATE TABLE current_relation_tags(relation_id bigint REFERENCES current_relations(id),
                    k text,v text,PRIMARY KEY(relation_id,k));
                CREATE TABLE relation_members(relation_id bigint,member_id bigint,member_role text,
                    member_type text,sequence_id bigint,
                    PRIMARY KEY(relation_id,member_type,member_id,member_role,sequence_id));
                CREATE TABLE current_relation_members(relation_id bigint REFERENCES current_relations(id),
                    member_id bigint,member_role text,member_type text,sequence_id bigint,
                    PRIMARY KEY(relation_id,member_type,member_id,member_role,sequence_id));
                INSERT INTO relations VALUES(1,1,'2020-01-01',true,1),(2,1,'2020-01-01',true,1);
                INSERT INTO relation_tags VALUES(1,'name','one'),(2,'name','two');
                INSERT INTO relation_members VALUES(1,1,'','Node',0),(2,2,'','Node',0);
            ''')
            old = subprocess.run(command+['-c','TRUNCATE TABLE current_relations;'],
                capture_output=True,text=True,timeout=15)
            if old.returncode == 0 or 'foreign key constraint' not in old.stderr:
                raise ValueError('Native preflight did not reproduce the original FK restriction')
            # Also retain one committed row: resuming must fill only missing keys.
            session.query('INSERT INTO current_relations SELECT * FROM relations WHERE relation_id=1;')
            pieces = [(name,0,2**63-1) for name in
                ('current_relations','current_relation_tags','current_relation_members')]
            levels = dependency_levels(pieces, [])
            counts = {}
            for level in levels:
                for name,lower,upper in level:
                    counts[name] = resume_table(session,name,io.StringIO(),time.monotonic()+30,
                                               lower_bound=lower,upper_bound=upper)['rows']
            if counts != {p[0]:2 for p in pieces}:
                raise ValueError('Native parent/child resume did not retain exact rows')
            session.query("UPDATE current_relation_tags SET v='incorrect' WHERE relation_id=1;")
            try: resume_table(session,'current_relation_tags',io.StringIO(),time.monotonic()+30)
            except ValueError as exc:
                if 'differs from history' not in str(exc): raise
            else: raise ValueError('Incorrect saved value was accepted or overwritten')
            if session.query("SELECT v FROM current_relation_tags WHERE relation_id=1;") != 'incorrect':
                raise ValueError('Failed comparison overwrote the original target row')
        result = dict(passed=True, native_postgres_major=11, original_fk_failure_reproduced=True,
            partial_parent_resume_exact=True, child_foreign_keys_preserved=True,
            wrong_value_rejected_without_overwrite=True, dependency_levels=levels,
            sentinel_sequence_failure_reproduced=True, sequence_cases=sequence_cases,
            seconds=time.monotonic()-began, large_checkpoint_restored=False, task_admissions=0)
        (output/'native-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
        return result
    finally:
        if server is not None and server.poll() is None:
            import os
            os.killpg(server.pid,signal.SIGINT)
            try: server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid,signal.SIGKILL);server.wait(timeout=5)
        log.close()
