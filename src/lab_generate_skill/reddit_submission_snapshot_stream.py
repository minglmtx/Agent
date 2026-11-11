"""One fresh indexed read-only native submission scan.

Preserves the legacy SHA256(md5(full row JSON) + newline, in native PK order)
and every column. Actual legacy/new/legacy full13 equality was verified in
job4498671. Each invocation opens a new transaction; no snapshot is cached.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time

CHUNK_ROWS = 2048
PHP = r'''$p=new PDO('pgsql:host=/state/run;port='.$argv[1].';dbname=postmill','postmill',null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_EMULATE_PREPARES=>false]);
try {
 $p->exec('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');
 $p->exec("SET LOCAL statement_timeout='20s'");
 $columns=$p->query("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='submissions' ORDER BY ordinal_position")->fetchAll(PDO::FETCH_COLUMN);
 if(!count($columns)||count(array_unique($columns))!==count($columns))throw new RuntimeException('Complete schema required');
 foreach($columns as $name)if(!is_string($name)||!preg_match('/^[a-z][a-z0-9_]*$/D',$name))throw new RuntimeException('Invalid native schema');
 $keys=$p->query("SELECT k.column_name FROM information_schema.table_constraints t JOIN information_schema.key_column_usage k ON k.constraint_schema=t.constraint_schema AND k.constraint_name=t.constraint_name AND k.table_name=t.table_name WHERE t.table_schema='public' AND t.table_name='submissions' AND t.constraint_type='PRIMARY KEY' ORDER BY k.ordinal_position")->fetchAll(PDO::FETCH_COLUMN);
 if($keys!==['id'])throw new RuntimeException('Actual native indexed id required');
 $total=(int)$p->query('SELECT count(*) FROM submissions')->fetchColumn();
 if($total<0)throw new RuntimeException('Exact nonnegative table count required');
 echo 'LAB_SUBMISSION_SCHEMA ',json_encode(['columns'=>$columns,'key'=>$keys,'reference_count'=>$total]),"\n";flush();
 $covered=0;$chunk=0;$last=null;$ctx=hash_init('sha256');$started=microtime(true);
 while($covered<$total) {
  $sql='SELECT id,md5(row_to_json(s)::text) AS row_md5 FROM submissions s'.($last===null?'':' WHERE id>CAST(? AS bigint)').' ORDER BY id LIMIT 2048';
  $q=$p->prepare($sql);$q->execute($last===null?[]:[$last]);$rows=$q->fetchAll(PDO::FETCH_ASSOC);$q->closeCursor();
  if(count($rows)!==min(2048,$total-$covered))throw new RuntimeException('Full native chunk coverage changed');
  foreach($rows as $row) {
   if(count($row)!==2||!array_key_exists('id',$row)||!array_key_exists('row_md5',$row))throw new RuntimeException('Exact native row checksum fields required');
   $text=(string)$row['id'];$id=(int)$text;$hash=$row['row_md5'];
   if(!preg_match('/^[1-9][0-9]*$/D',$text)||(string)$id!==$text||($last!==null&&$id<=$last)||!is_string($hash)||!preg_match('/^[0-9a-f]{32}$/D',$hash))throw new RuntimeException('Ordered complete native row checksums required');
   hash_update($ctx,$hash."\n");$last=$id;
  }
  $covered+=count($rows);$chunk++;
  echo 'LAB_SUBMISSION_CHUNK ',json_encode(['table'=>'submissions','chunk'=>$chunk,'rows'=>count($rows),'covered'=>$covered,'total'=>$total,'seconds'=>microtime(true)-$started]),"\n";flush();
 }
 if((int)$p->query('SELECT count(*) FROM submissions')->fetchColumn()!==$total)throw new RuntimeException('Full table count changed');
 $p->exec('ROLLBACK');
 echo 'LAB_SUBMISSION_RESULT ',json_encode(['count'=>$total,'columns'=>$columns,'key'=>$keys,'sha256'=>hash_final($ctx)]),"\n";flush();
}catch(Throwable $e){if($p->inTransaction())$p->rollBack();$state=$e instanceof PDOException?($e->errorInfo[0]??null):null;fwrite(STDERR,'LAB_SUBMISSION_ERROR '.json_encode(['sqlstate'=>$state])."\n");exit(42);}'''


class StreamValidation:
    """Only safe progress metadata leaves the isolated native process."""
    def __init__(self, output):
        from .progress_log import ProgressLog
        self.output = Path(output) if output is not None else None
        self.log = ProgressLog(self.output)
        self.schema = None; self.result = None; self.covered = 0; self.chunks = 0

    def line(self, text):
        if self.result is not None:
            raise ValueError("Native stream data appeared after the final full-table result")
        if text.startswith("LAB_SUBMISSION_SCHEMA "):
            value = json.loads(text[len("LAB_SUBMISSION_SCHEMA "):])
            if self.schema is not None or set(value) != {"columns", "key", "reference_count"}:
                raise ValueError("One complete native schema required")
            cols = value["columns"]
            if (not isinstance(cols, list) or not cols or len(cols) != len(set(cols)) or
                    any(not isinstance(x, str) or not re.fullmatch('[a-z][a-z0-9_]*', x) for x in cols) or
                    value["key"] != ["id"] or type(value["reference_count"]) is not int or value["reference_count"] < 0):
                raise ValueError("Exact full native schema/primary key/count required")
            self.schema = value
        elif text.startswith("LAB_SUBMISSION_CHUNK "):
            value = json.loads(text[len("LAB_SUBMISSION_CHUNK "):])
            if self.schema is None or set(value) != {"table", "chunk", "rows", "covered", "total", "seconds"}:
                raise ValueError("Native progress lacks its complete schema")
            expected_rows = min(CHUNK_ROWS, self.schema["reference_count"] - self.covered)
            if (value["table"] != "submissions" or type(value["chunk"]) is not int or value["chunk"] != self.chunks + 1 or
                    type(value["rows"]) is not int or value["rows"] != expected_rows or expected_rows <= 0 or
                    type(value["covered"]) is not int or value["covered"] != self.covered + expected_rows or
                    type(value["total"]) is not int or value["total"] != self.schema["reference_count"] or
                    type(value["seconds"]) not in (int, float) or not math.isfinite(value["seconds"]) or value["seconds"] < 0):
                raise ValueError("Native progress omitted/repeated rows or changed full coverage")
            self.covered = value["covered"]; self.chunks = value["chunk"]
            self.log.record('submissions', value)
        elif text.startswith("LAB_SUBMISSION_RESULT "):
            value = json.loads(text[len("LAB_SUBMISSION_RESULT "):])
            if (self.schema is None or set(value) != {"count", "columns", "key", "sha256"} or
                    type(value["count"]) is not int or value["count"] != self.covered or
                    value["count"] != self.schema["reference_count"] or value["columns"] != self.schema["columns"] or
                    value["key"] != self.schema["key"] or not isinstance(value["sha256"], str) or
                    not re.fullmatch('[0-9a-f]{64}', value["sha256"])):
                raise ValueError("Native final checksum is not the exact complete row/column result")
            if value["count"] == 0 and value["sha256"] != hashlib.sha256(b'').hexdigest():
                raise ValueError("Empty native table checksum mismatch")
            self.result = value
        elif text.strip():
            raise ValueError("Unexpected native submission stream output")

    def finish(self, returncode):
        self.log.flush()
        if returncode != 0 or self.result is None:
            raise ValueError("Native submission stream failed or omitted its final full-table checksum")
        return self.result


def submission_snapshot(site, out, *, timeout=150):
    if getattr(site, 'domain', None) != 'reddit' or not isinstance(getattr(site, 'base', None), list):
        raise ValueError("Actual isolated native Reddit command required")
    if type(timeout) is not int or timeout <= 0:
        raise ValueError("Finite fresh native stream timeout required")
    parser = StreamValidation(out)
    process = subprocess.Popen(site.base + ['php', '-r', PHP, str(site.db_port)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    selector = selectors.DefaultSelector(); buffers = {}; deadline = time.monotonic() + timeout
    for stream in (process.stdout, process.stderr):
        os.set_blocking(stream.fileno(), False); selector.register(stream, selectors.EVENT_READ); buffers[stream] = b''
    def line(stream, value):
        text = value.decode('utf-8', errors='strict')
        if stream is process.stderr:
            if text.startswith('LAB_SUBMISSION_ERROR '):
                raise RuntimeError('Fresh native submission checksum command failed')
            # Never publish private native database stderr.
        else:
            parser.line(text)
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Fresh complete native submission scan exceeded its finite deadline")
            for key, _ in selector.select(min(remaining, 1)):
                stream = key.fileobj; data = os.read(stream.fileno(), 65536)
                if not data:
                    if buffers[stream]: line(stream, buffers[stream])
                    selector.unregister(stream); continue
                buffers[stream] += data
                if len(buffers[stream]) > 1048576:
                    raise ValueError("Oversized native checksum operational metadata")
                while b'\n' in buffers[stream]:
                    piece, buffers[stream] = buffers[stream].split(b'\n', 1); line(stream, piece)
        return parser.finish(process.wait(timeout=max(.01, deadline - time.monotonic())))
    finally:
        if process.poll() is None:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        process.wait(timeout=5)
        selector.close(); process.stdout.close(); process.stderr.close()
        parser.log.flush()


def complete_snapshot(site, out):
    """Keep the exact original full13 tables/columns and ignored-column policy."""
    from .reddit_exact_forum_runtime import protected_snapshot
    from .reddit_protected_chunks import validate_snapshot
    from .site_database import select_rows
    from .reddit_native_read_protection import VERSION
    names = ','.join("'" + name + "'" for name in (
        'forums', 'comments', 'submission_votes', 'comment_votes', 'wiki_pages',
        'wiki_revisions', 'forum_tags', 'forums_tags', 'hidden_forums',
        'forum_subscriptions', 'user_blocks', 'users'))
    present = select_rows(site, "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN (" + names + ') ORDER BY table_name')
    if not isinstance(present, list) or len(present) != 12 or len({row.get('table_name') for row in present}) != 12:
        raise ValueError('Every original declared protected table must exist')
    task_tables = protected_snapshot(site); validate_snapshot(task_tables)
    return {'version': VERSION, 'twelve_task_tables': task_tables,
            'submissions': submission_snapshot(site, out), 'users_only_ignored_column': 'last_seen'}
