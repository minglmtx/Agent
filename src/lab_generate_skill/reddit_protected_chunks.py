"""Full native protected tables through bounded primary-key chunks.

One persistent read-only REPEATABLE READ connection scans every row/column.
Only PK values and full-row hashes leave PostgreSQL; progress never contains
those private values. No sampling and no raised SQL statement timeout.
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
from .site_database import select_rows
from .progress_log import ProgressLog

VERSION='reddit-complete-protected-chunks-v3'
TABLES={'comments','comment_votes','submission_votes','users'}
TYPES={'bigint':'bigint','integer':'integer','smallint':'smallint','uuid':'uuid'}
CHUNK_ROWS=2048

PHP=r'''$spec=json_decode($argv[2],true,512,JSON_THROW_ON_ERROR);
$p=new PDO('pgsql:host=/state/run;port='.$argv[1].';dbname=postmill','postmill',null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_EMULATE_PREPARES=>false]);
$started=microtime(true);$result=[];
try {
 $p->exec('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');
 $p->exec("SET LOCAL statement_timeout='20s'");
 foreach($spec as $table=>$columns) {
  if(!in_array($table,['comments','comment_votes','submission_votes','users'],true)||!is_array($columns)||!count($columns)) throw new RuntimeException('Invalid protected specification');
  $names=[];$types=[];
  foreach($columns as $column) {
   if(!preg_match('/^[a-z][a-z0-9_]*$/D',$column['name'])||!in_array($column['type'],['bigint','integer','smallint','uuid'],true)) throw new RuntimeException('Invalid native primary key');
   $names[]='"'.$column['name'].'"';$types[]=$column['type'];
  }
  $last=null;$total=0;$chunk=0;$ctx=hash_init('md5');
  while(true) {
   $parameters=[];$condition='';
   if($last!==null) {
    $casts=[];foreach($types as $i=>$type){$casts[]='CAST(? AS '.$type.')';$parameters[]=$last[$i];}
    $condition=' WHERE ROW('.implode(',',$names).') > ROW('.implode(',',$casts).')';
   }
   $projection=$table==='users' ? "(to_jsonb(r)-'last_seen')::text" : 'row_to_json(r)::text';
   $sql='SELECT '.implode(',',$names).',md5('.$projection.') AS "__lab_row_hash" FROM "'.$table.'" r'.$condition.' ORDER BY '.implode(',',$names).' LIMIT 2048';
   $q=$p->prepare($sql);$q->execute($parameters);$rows=$q->fetchAll(PDO::FETCH_ASSOC);$q->closeCursor();
   if(!count($rows)) break;
   foreach($rows as $row) {
    $h=$row['__lab_row_hash'];if(!is_string($h)||!preg_match('/^[0-9a-f]{32}$/D',$h)) throw new RuntimeException('Invalid row checksum');
    $key=[];
    foreach($columns as $i=>$column) {
     $value=$row[$column['name']];$text=(string)$value;
     if($types[$i]==='uuid') {if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/D',$text)) throw new RuntimeException('Invalid native UUID key');}
     else {if(!preg_match('/^-?(0|[1-9][0-9]*)$/D',$text)) throw new RuntimeException('Invalid native integer key');}
     $key[]=$text;
    }
    hash_update($ctx,$h);$last=$key;
   }
   $total+=count($rows);$chunk++;
   echo 'LAB_PROTECTED_CHUNK ',json_encode(['table'=>$table,'chunk'=>$chunk,'rows'=>count($rows),'total'=>$total,'seconds'=>microtime(true)-$started]),"\n";flush();
  }
  $reference=(int)$p->query('SELECT count(*) FROM "'.$table.'"')->fetchColumn();
  if($reference!==$total)throw new RuntimeException('Primary-key scan coverage mismatch');
  $result[$table]=['count'=>$total,'digest'=>hash_final($ctx),'chunks'=>$chunk,'reference_count'=>$reference];
 }
 $p->exec('ROLLBACK');
 echo 'LAB_PROTECTED_RESULT ',json_encode($result),"\n";flush();
} catch(Throwable $e) {
 if($p->inTransaction())$p->rollBack();
 $state=$e instanceof PDOException ? ($e->errorInfo[0]??null) : null;
 fwrite(STDERR,'LAB_PROTECTED_ERROR '.json_encode(['sqlstate'=>$state])."\n");exit(42);
}'''


def primary_keys(site,tables):
    if not tables or len(set(tables))!=len(tables)or any(t not in TABLES for t in tables):raise ValueError('Known distinct heavy tables required')
    names=','.join("'"+t+"'"for t in tables)
    sql="SELECT k.table_name,k.column_name,k.ordinal_position,c.data_type FROM information_schema.table_constraints t JOIN information_schema.key_column_usage k ON k.constraint_name=t.constraint_name AND k.constraint_schema=t.constraint_schema AND k.table_name=t.table_name JOIN information_schema.columns c ON c.table_schema=k.table_schema AND c.table_name=k.table_name AND c.column_name=k.column_name WHERE t.constraint_type='PRIMARY KEY' AND k.table_schema='public' AND k.table_name IN ("+names+") ORDER BY k.table_name,k.ordinal_position"
    rows=select_rows(site,sql);spec={t:[]for t in tables}
    for r in rows:
        table,name,kind,pos=r.get('table_name'),r.get('column_name'),r.get('data_type'),r.get('ordinal_position')
        if(table not in spec or not isinstance(name,str)or not re.fullmatch('[a-z][a-z0-9_]*',name)or kind not in TYPES or type(pos)is not int or pos!=len(spec[table])+1):raise ValueError('Malformed native primary-key schema')
        if name in {v['name']for v in spec[table]}:raise ValueError('Duplicate native primary key')
        spec[table].append({'name':name,'type':TYPES[kind]})
    if any(not cols for cols in spec.values()):raise ValueError('A full native indexed primary key is required')
    return spec


def _stop(proc):
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:raise RuntimeError('Protected checksum process group did not stop')


def run_chunk_stream(site,spec,*,timeout=600):
    if getattr(site,'domain',None)!='reddit'or not hasattr(site,'base'):raise ValueError('Native isolated Reddit command required')
    if type(timeout)is not int or timeout<=0:raise ValueError('Bounded stream deadline required')
    started=time.monotonic();deadline=started+timeout;progress={t:{'chunk':0,'total':0}for t in spec};final=None
    proc=subprocess.Popen(site.base+['php','-r',PHP,str(site.db_port),json.dumps(spec)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    selector=selectors.DefaultSelector();buffers={};errors=[]
    for stream in(proc.stdout,proc.stderr):
        os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ);buffers[stream]=b''
    output=Path(site.logs)/'protected-chunk-progress.jsonl';output.parent.mkdir(parents=True,exist_ok=True)
    log=ProgressLog(output)
    def line(stream,data):
        nonlocal final
        text=data.decode('utf-8',errors='strict')
        if stream is proc.stderr:
            if text.startswith('LAB_PROTECTED_ERROR '):
                r=json.loads(text[len('LAB_PROTECTED_ERROR '):]);code=r.get('sqlstate')
                errors.append({'sqlstate':code if isinstance(code,str)and re.fullmatch('[0-9A-Z]{5}',code)else None})
            return
        if text.startswith('LAB_PROTECTED_CHUNK '):
            r=json.loads(text[len('LAB_PROTECTED_CHUNK '):]);table=r.get('table');previous=progress.get(table)
            if(previous is None or type(r.get('chunk'))is not int or r['chunk']!=previous['chunk']+1
               or type(r.get('rows'))is not int or not 0<r['rows']<=CHUNK_ROWS or type(r.get('total'))is not int
               or r['total']!=previous['total']+r['rows']or type(r.get('seconds'))not in(int,float)or not math.isfinite(r['seconds'])or r['seconds']<0):raise ValueError('Incomplete or noncontiguous chunk progress')
            progress[table]={'chunk':r['chunk'],'total':r['total']}
            # Exactly the public operational metadata, never row hashes/PKs.
            log.record(table,{k:r[k]for k in('table','chunk','rows','total','seconds')})
        elif text.startswith('LAB_PROTECTED_RESULT '):
            if final is not None:raise ValueError('Duplicate protected result')
            final=json.loads(text[len('LAB_PROTECTED_RESULT '):])
        elif text.strip():raise ValueError('Unexpected protected output')
    try:
        while selector.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Full protected-table scan exceeded its absolute stream deadline')
            for key,_ in selector.select(min(remaining,1)):
                stream=key.fileobj;data=os.read(stream.fileno(),65536)
                if not data:
                    if buffers[stream]:line(stream,buffers[stream]);buffers[stream]=b''
                    selector.unregister(stream);continue
                buffers[stream]+=data
                if len(buffers[stream])>1048576:raise ValueError('Oversized protected progress')
                while b'\n'in buffers[stream]:
                    piece,buffers[stream]=buffers[stream].split(b'\n',1);line(stream,piece)
        code=proc.wait(timeout=max(.01,deadline-time.monotonic()))
        if code!=0 or errors:raise RuntimeError('Bounded protected SQL scan failed; see safe chunk progress')
        if not isinstance(final,dict)or set(final)!=set(spec):raise ValueError('Incomplete full-table result')
        for table,r in final.items():
            if(not isinstance(r,dict)or type(r.get('count'))is not int or r['count']<0 or type(r.get('chunks'))is not int
               or r['count']!=progress[table]['total']or r['chunks']!=progress[table]['chunk']or type(r.get('reference_count'))is not int or r['reference_count']!=r['count']or not isinstance(r.get('digest'),str)
               or not re.fullmatch('[0-9a-f]{32}',r['digest'])):raise ValueError('Final checksum does not cover all recorded chunks')
        if any(r['count']==0 and r['digest']!=hashlib.md5(b'').hexdigest()for r in final.values()):raise ValueError('Empty native table checksum mismatch')
        return {t:{'count':r['count'],'digest':r['digest']}for t,r in final.items()}
    finally:
        _stop(proc);selector.close();proc.stdout.close();proc.stderr.close()
        log.flush()


def full_digest(site,tables,*,timeout=600):
    return run_chunk_stream(site,primary_keys(site,tables),timeout=timeout)


def validate_snapshot(value):
    required={'forums','comments','submission_votes','comment_votes','wiki_pages','wiki_revisions','forum_tags','forums_tags','hidden_forums','forum_subscriptions','user_blocks','users'}
    if not isinstance(value,dict)or set(value)!=required:raise ValueError('Complete native protected table set required')
    for row in value.values():
        if not isinstance(row,dict)or set(row)!={'count','digest'}or type(row['count'])is not int or row['count']<0 or not isinstance(row['digest'],str)or not re.fullmatch('[0-9a-f]{32}',row['digest']):raise ValueError('Malformed native table coverage/checksum')


def require_restored_proof(proof):
    """Never promote an old proof to the new full-user protection protocol."""
    cycles=proof.get('cycles')
    if proof.get('protection_version')!=VERSION or not isinstance(cycles,list)or len(cycles)!=2:raise ValueError('New two-fresh complete protection proof required')
    for cycle in cycles:
        if cycle.get('protection_version')!=VERSION:raise ValueError('Fresh-cycle protection version mismatch')
        before=cycle.get('private_protected_before');after=cycle.get('private_protected_after')
        validate_snapshot(before);validate_snapshot(after)
        if before!=after:raise ValueError('Whole native table restoration mismatch')
    if cycles[0]['private_protected_before']!=cycles[1]['private_protected_before']:raise ValueError('Fresh full native table baseline mismatch')
