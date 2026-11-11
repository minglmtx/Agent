"""Private native CSV controls; no actor tools, guessed filter, or CSV synthesis.

Only exact jobs observed after trusted native UI confirmation may be consumed.
The unchanged installed worker/finder/export/Notify chain creates the attachment.
Full protected records and the independent raw-record oracle remain private.
"""
from collections import Counter
import hashlib
import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
import re
from urllib.parse import urlsplit
from .gitlab_native_csv_delivery import completion, DELIVERY_ADAPTER_RUBY
from .site_database import select_rows

VERSION = 'gitlab-real-native-csv-controls-v5'
KINDS = {'issues': 'issue', 'merge_requests': 'merge_request'}
PROTECTED_TABLES = ('projects','namespaces','routes','issues','merge_requests','users',
    'issue_assignees','merge_request_assignees','milestones','labels','label_links',
    'timelogs','approvals','merge_request_metrics','project_authorizations','members')
AUTH_COLUMNS = ('sign_in_count','current_sign_in_at','last_sign_in_at','current_sign_in_ip',
    'last_sign_in_ip','remember_created_at','last_activity_on','updated_at')
REDIS = ['/opt/gitlab/embedded/bin/redis-cli','--raw','-s','/var/opt/gitlab/redis/redis.socket']
CLAIM_LUA = r'''local raw=ARGV[1]; local jid=ARGV[2]; local expected=ARGV[3]; local item=cjson.decode(raw)
if expected~='IssuableExportCsvWorker' and expected~='RepositoryImportWorker' then return -1 end
if item['jid']~=jid or item['class']~=expected then return -1 end
local copies=0
for _,value in ipairs(redis.call('LRANGE',KEYS[1],0,-1)) do if value==raw then copies=copies+1 end end
if copies~=1 then return -2 end
return redis.call('LREM',KEYS[1],1,raw)'''


def private_json(path, value):
    from .io_utils import json_text
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.parent.chmod(0o700)
    with path.open('x') as file:
        path.chmod(0o600); file.write(json_text(value))


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


# Native Omnibus Redis disables KEYS. A complete read-only atomic SCAN avoids
# that command without un-renaming it or weakening queue/payload protection.
# Cursor/count envelopes also preserve Lua cjson's actual empty {} encoding.
QUEUE_SCAN_MAX_PAGES = 4096
QUEUE_KEYS_LUA = r"""local cursor='0';local found={};local keys={};local pages=0
local limit=tonumber(ARGV[2]);local page_limit=tonumber(ARGV[3])
repeat
 pages=pages+1
 if pages>page_limit then
  return cjson.encode({kind='native_queue_keys',count=#keys,keys=keys,complete_scan=false,scan_pages=pages-1,cursor=cursor,scan_budget_exceeded=true})
 end
 local page=redis.call('SCAN',cursor,'MATCH',ARGV[1],'COUNT',512)
 cursor=page[1]
 for _,key in ipairs(page[2]) do
  if not found[key] then found[key]=true;keys[#keys+1]=key end
  if #keys>limit then
   return cjson.encode({kind='native_queue_keys',count=#keys,keys=keys,complete_scan=false,scan_pages=pages,cursor=cursor,over_budget=true})
  end
 end
until cursor=='0'
return cjson.encode({kind='native_queue_keys',count=#keys,keys=keys,complete_scan=true,scan_pages=pages,cursor=cursor})"""
QUEUE_VALUES_LUA = r"""local value=redis.call('TYPE',KEYS[1]);local kind=value['ok']
if kind~='list' then return cjson.encode({kind='native_queue_values',type=kind}) end
local count=redis.call('LLEN',KEYS[1])
if count>tonumber(ARGV[1]) then
 return cjson.encode({kind='native_queue_values',type=kind,count=count,over_budget=true})
end
return cjson.encode({kind='native_queue_values',type=kind,count=count,values=redis.call('LRANGE',KEYS[1],0,-1)})"""


class QueueSnapshotError(ValueError):
    """Stage/count/hash metadata only; never payloads or credential-bearing stderr."""
    def __init__(self, stage, error, *, queue=None, count=None, response=None):
        self.record={'stage':stage,'exception_type':type(error).__name__,
                     'returncode':getattr(error,'returncode',None)}
        if queue is not None:self.record['queue_key_sha256']=hashlib.sha256(queue.encode()).hexdigest()
        if type(count)is int:self.record['native_count']=count
        if isinstance(response,str):
            self.record.update(response_bytes=len(response.encode()),response_sha256=hashlib.sha256(response.encode()).hexdigest())
            prefix=response.lstrip().split(' ',1)[0]
            if prefix in ('ERR','NOAUTH','NOPERM','WRONGTYPE','BUSY','LOADING','OOM'):
                self.record['native_cli_error_code']=prefix
                self.record['native_unknown_command_called_from_lua']=('Unknown Redis command called from script'in response)
        super().__init__('Complete native queue capture failed at '+stage)

    def safe_record(self):return dict(self.record)


def _native_vector(value, *, field, count):
    # The bundled Lua cjson encodes an actual empty table as {}. Only count=0
    # authorizes that representation; null, boolean counts, or partial data fail.
    items=value.get(field)
    if type(count)is not int or count<0:raise ValueError('Native queue count is not a nonnegative integer')
    if count==0 and items=={}:items=[]
    if not isinstance(items,list)or len(items)!=count or any(not isinstance(item,str)for item in items):
        raise ValueError('Native queue vector/count schema differs')
    return items


def queue_snapshot(site, progress=None):
    """Capture every native queue/payload within the original strict budgets."""
    def event(value):
        if progress is not None:
            path=Path(progress);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with path.open('a')as file:path.chmod(0o600);file.write(json.dumps(value,sort_keys=True)+'\n')
    def read(stage, args, *, queue=None):
        began=time.monotonic();response=None;count=None
        try:
            response=site.command(REDIS+args,capture_output=True,text=True,timeout=20).stdout
            value=json.loads(response)
            if not isinstance(value,dict):raise ValueError('Native Redis envelope is not an object')
            count=value.get('count')
            event({'stage':stage,'status':'received','seconds':time.monotonic()-began,
                   'native_count':count if type(count)is int else None,
                   'response_bytes':len(response.encode()),'response_sha256':hashlib.sha256(response.encode()).hexdigest()})
            return value,response
        except Exception as error:
            wrapped=QueueSnapshotError(stage,error,queue=queue,count=count,response=response)
            event(dict(wrapped.safe_record(),status='error',seconds=time.monotonic()-began));raise wrapped from error
    value,response=read('queue_discovery',['EVAL',QUEUE_KEYS_LUA,'0','resque:gitlab:queue:*','256',str(QUEUE_SCAN_MAX_PAGES)])
    try:
        if value.get('kind')!='native_queue_keys':raise ValueError('Native discovery envelope kind differs')
        if (value.get('complete_scan')is not True or value.get('cursor')!='0'
                or type(value.get('scan_pages'))is not int or not 1<=value['scan_pages']<=QUEUE_SCAN_MAX_PAGES
                or value.get('over_budget')is not None or value.get('scan_budget_exceeded')is not None):
            raise ValueError('Native queue cursor scan is incomplete or exceeds its unchanged scope budget')
        keys=_native_vector(value,field='keys',count=value.get('count'))
        if len(keys)>256 or len(set(keys))!=len(keys)or any(not re.fullmatch(r'resque:gitlab:queue:[A-Za-z0-9_:.-]+',key)for key in keys):
            raise ValueError('Native queue schema or discovery budget exceeded')
    except Exception as error:
        wrapped=QueueSnapshotError('queue_discovery_schema',error,count=value.get('count'),response=response)
        event(dict(wrapped.safe_record(),status='error'));raise wrapped from error
    scan_pages=value['scan_pages']
    rows=[]
    for key in sorted(keys):
        value,response=read('queue_payloads',['EVAL',QUEUE_VALUES_LUA,'1',key,'50000'],queue=key)
        try:
            if value.get('kind')!='native_queue_values'or value.get('type')!='list':
                raise ValueError('Native queue is not an existing list')
            count=value.get('count')
            if type(count)is not int or count<0 or count>50000 or value.get('over_budget')is not None:
                raise ValueError('Full native queue budget exceeded or malformed; no partial capture accepted')
            values=_native_vector(value,field='values',count=count)
            for raw in values:
                job=json.loads(raw)
                if not isinstance(job,dict):raise ValueError('Native queued payload is not a job')
                rows.append({'queue':key,'raw':raw,'job':job})
        except Exception as error:
            wrapped=QueueSnapshotError('queue_payload_schema',error,queue=key,count=value.get('count'),response=response)
            event(dict(wrapped.safe_record(),status='error'));raise wrapped from error
    event({'stage':'queue_snapshot_complete','status':'complete','queues':len(keys),'jobs':len(rows),
           'complete_namespace_captured':True,'namespace_scan_complete':True,'scan_pages':scan_pages,
           'queue_key_limit':256,'per_queue_job_limit':50000,'scan_page_limit':QUEUE_SCAN_MAX_PAGES})
    return rows



NATIVE_LIST_ISSUE_TYPES = ('issue', 'incident', 'test_case', 'task', 'objective')


def native_export_discovery_capture(before, after):
    """Private safe metadata saved before any correlation/filter rejection.

    Keep every newly observed native CSV JID and filter key/type/emptiness. Only
    boolean/numeric values and known native enum/identity fields are returned;
    arbitrary strings/containers are hashed so tokens and search bodies cannot
    leak into the report. Full original bytes remain unchanged in memory.
    """
    old = Counter((row['queue'], row['raw']) for row in before)
    current = Counter((row['queue'], row['raw']) for row in after)
    additions = current - old
    seen = set(); captures = []
    for row in after:
        identity = (row['queue'], row['raw'])
        if additions[identity] <= 0 or identity in seen or row['job'].get('class') != 'IssuableExportCsvWorker':
            continue
        seen.add(identity)
        job = row['job']; args = job.get('args')
        value = {'native_class': 'IssuableExportCsvWorker',
                 'native_jid': job.get('jid') if isinstance(job.get('jid'), str) and re.fullmatch(r'[0-9a-f]{24,32}', job['jid']) else None,
                 'queue_key_sha256': hashlib.sha256(row['queue'].encode()).hexdigest(),
                 'raw_job_sha256': hashlib.sha256(row['raw'].encode()).hexdigest(),
                 'observed_copies': additions[identity],
                 'argument_count': len(args) if isinstance(args, list) else None,
                 'filter_metadata': [], 'correlation_validated': False}
        if isinstance(args, list) and len(args) == 4:
            value['native_kind'] = args[0] if args[0] in ('issue', 'merge_request') else None
            value['native_user_id'] = args[1] if type(args[1]) is int else None
            value['native_project_id'] = args[2] if type(args[2]) is int else None
            if isinstance(args[3], dict):
                for key, item in sorted(args[3].items(), key=lambda pair: str(pair[0])):
                    empty = item is None or item == '' or type(item) is list and not item
                    field = {'key': key if isinstance(key, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', key) else 'invalid_key_sha256:' + digest(key), 'json_type': type(item).__name__, 'empty': empty}
                    sensitive_key = bool(re.search(r'auth|token|password|secret|cookie|session|api.?key|credential', str(key), re.I))
                    if sensitive_key:
                        field['value_sha256'] = digest(item)
                        field['raw_value_not_recorded'] = True
                    elif item is None or type(item) in (bool, int, float):
                        field['value'] = item
                    elif key == 'issue_types' and type(item) is list and len(item) <= 7 and all(type(part) is str and part in NATIVE_LIST_ISSUE_TYPES for part in item):
                        field['value'] = item
                    elif type(item) is str and key in ('state', 'scope', 'sort', 'project_id') and re.fullmatch(r'[A-Za-z0-9_.-]{0,80}', item):
                        field['value'] = item
                    else:
                        field['value_sha256'] = digest(item)
                        field['raw_value_not_recorded'] = True
                    value['filter_metadata'].append(field)
        captures.append(value)
    return {'version': 'native-csv-private-discovery-metadata-v1',
            'actual_new_native_export_jobs': len(captures), 'jobs': captures,
            'pre_existing_jobs_preserved': not bool(old - current),
            'full_native_queue_mutation': False, 'private_only': True,
            'actor_or_teacher_input': False, 'raw_payload_or_credentials_saved': False}


def new_export_job(before,after,*,kind,user_id,project_id,state):
    if kind not in KINDS.values() or state not in ('opened','closed','all','merged') or kind=='issue' and state=='merged':
        raise ValueError('Explicit native collection and state required')
    for ident in (user_id,project_id):
        if type(ident) is not int or ident<=0: raise ValueError('Private native account/project ID required')
    old=Counter((r['queue'],r['raw'])for r in before); current=Counter((r['queue'],r['raw'])for r in after)
    if old-current: raise ValueError('Pre-existing native jobs disappeared during UI confirmation')
    changes=current-old
    additions=[r for r in after if changes[(r['queue'],r['raw'])]>0 and r['job'].get('class')=='IssuableExportCsvWorker']
    if len(additions)!=1: raise ValueError('Native UI must create exactly one correlated export job')
    record=additions[0]; job=record['job']; args=job.get('args')
    if not isinstance(job.get('jid'),str)or not re.fullmatch(r'[0-9a-f]{24,32}',job['jid']):
        raise ValueError('Real native queue JID missing')
    if not isinstance(args,list)or len(args)!=4 or args[:3]!=[kind,user_id,project_id] or any(type(v)is not int for v in args[1:3]):
        raise ValueError('Native queued collection/account/project arguments differ')
    params=args[3]
    if not isinstance(params,dict)or params.get('state')!=state:
        raise ValueError('Native queued list state does not match actual UI filter')
    # Confidential False is a real public-only selection; even empty string
    # is not an independently supported no-filter contract. Native default is nil.
    if 'confidential' in params and params['confidential'] is not None:
        raise ValueError('Independent oracle does not yet support this native confidential selection')
    allowed={'state','sort','scope','project_id','include_subgroups','non_archived','attempt_project_search_optimizations','issue_types'}
    if 'issue_types' in params and params['issue_types'] not in (None, []):
        types=params['issue_types']
        if kind!='issue' or type(types)is not list or len(types)!=len(NATIVE_LIST_ISSUE_TYPES) or any(type(item)is not str for item in types) or set(types)!=set(NATIVE_LIST_ISSUE_TYPES):
            raise ValueError('Independent oracle only supports the complete installed native issue-list type set')
    # Installed IssuableCollections always adds this true project flag. It only
    # chooses a CTE when search is present; nonempty search remains rejected.
    # Keep the native argument untouched and do not allow group/search filters.
    if 'attempt_project_search_optimizations' in params and params['attempt_project_search_optimizations'] is not True:
        raise ValueError('Native project optimization flag differs from the installed boolean default')
    if any(k not in allowed and v not in (None,'',[]) for k,v in params.items()):
        raise ValueError('Independent oracle does not yet support this nonempty native filter')
    if params.get('scope') not in (None,'','all') or params.get('project_id') not in (None,'',project_id,str(project_id)):
        raise ValueError('Native export scope differs from current project')
    if params.get('include_subgroups') not in (None,'',False,'false') or params.get('non_archived') not in (None,'',True,'true'):
        raise ValueError('Unsupported native subgroup/archive filter')
    return record


def claim_job(site,record,*,expected_class='IssuableExportCsvWorker'):
    job=record['job']; raw=record['raw']
    if json.loads(raw)!=job: raise ValueError('Native queued bytes changed before exact claim')
    if expected_class not in ('IssuableExportCsvWorker','RepositoryImportWorker') or job.get('class')!=expected_class:
        raise ValueError('Observed job class differs from explicitly authorized consumer')
    result=site.command(REDIS+['EVAL',CLAIM_LUA,'1',record['queue'],raw,job['jid'],expected_class],capture_output=True,text=True,timeout=20)
    if result.returncode!=0:raise ValueError('Native atomic job claim transport failed')
    value=result.stdout.strip()
    if value!='1': raise ValueError('Exact observed native job could not be atomically claimed once')
    return {'job_id':job['jid'],'queue':record['queue'],'raw_sha256':hashlib.sha256(raw.encode()).hexdigest(),'claim_count':1,'only_observed_jid_claimed':True}


def existing_jobs_preserved(before,after,claimed):
    old=Counter((r['queue'],r['raw'])for r in before); current=Counter((r['queue'],r['raw'])for r in after)
    return not bool(old-current) and not any(r['job'].get('jid')in set(claimed) for r in after)


class ProtectedSnapshotError(RuntimeError):
    """Stage metadata only; never SQL, native rows or credential-bearing stderr."""
    def __init__(self, table, stage, error):
        self.table, self.stage = table, stage
        self.returncode = getattr(error, 'returncode', None)
        self.exception_type = type(error).__name__
        self.sqlstate = None
        stderr = getattr(error, 'stderr', '') or ''
        if isinstance(stderr, bytes): stderr = stderr.decode(errors='replace')
        match = re.search(r'ERROR:\s+([0-9A-Z]{5}):', stderr)
        if match: self.sqlstate = match[1]
        super().__init__('Private native protected snapshot failed at '+table+':'+stage)

    def safe_record(self):
        return {'table': self.table, 'stage': self.stage, 'exception_type': self.exception_type,
                'returncode': self.returncode, 'sqlstate': self.sqlstate,
                'raw_sql_stderr_rows_credentials_not_saved': True}


def unique_key_query(table):
    if table not in PROTECTED_TABLES:
        raise ValueError('Only declared protected tables may be inspected')
    return "SELECT i.indexrelid, i.indisprimary, array_agg(a.attname ORDER BY k.ord) AS names FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum,ord) ON true JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum WHERE c.oid='public."+table+"'::regclass AND i.indisunique AND i.indpred IS NULL AND i.indexprs IS NULL AND a.attnotnull GROUP BY i.indexrelid,i.indisprimary,i.indkey HAVING count(*)=array_length(i.indkey::smallint[],1) ORDER BY i.indisprimary DESC,i.indexrelid LIMIT 1"


def protected_snapshot(site,progress=None,*,chunk_size=2048,reader=None):
    """All rows/all columns of the declared 16 protected tables, with native 20s SQL limits."""
    if type(chunk_size)is not int or not 1<=chunk_size<=4096: raise ValueError('Bounded complete chunk size required')
    result={}
    def read(table,stage,sql):
        try:return (select_rows if reader is None else reader)(site,sql)
        except Exception as error:
            safe=ProtectedSnapshotError(table,stage,error)
            if progress:
                with Path(progress).open('a')as file:file.write(json.dumps({'status':'failed',**safe.safe_record(),'statement_timeout_seconds':20})+'\n')
            raise safe from None
    for table in PROTECTED_TABLES:
        columns=read(table,'column_discovery',"SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='"+table+"' ORDER BY ordinal_position")
        if not columns: raise ValueError('Required protected table missing: '+table)
        keys=read(table,'unique_key_discovery',unique_key_query(table))
        names=keys[0]['names'] if len(keys)==1 else None
        if not isinstance(names,list)or not names or any(not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',n)for n in names):
            raise ValueError('Complete protected traversal requires native unique nonnullable keys: '+table)
        total=read(table,'initial_count','SELECT COUNT(*) AS n FROM "'+table+'"')[0]['n']; offset=0; hasher=hashlib.sha256(); chunks=0
        order=','.join('"'+n+'"'for n in names)
        types={r['column_name']:r.get('data_type') for r in columns}
        keyset=all(types.get(n) in ('smallint','integer','bigint') for n in names)
        cursor=None
        while offset<total:
            projection='md5(row_to_json(t)::text) AS digest'
            clause=''
            if keyset:
                projection+=',json_build_array('+order+') AS native_key'
                if cursor is not None:
                    clause=' WHERE ('+order+')>('+','.join(map(str,cursor))+')'
            else:
                clause=''
            sql='SELECT '+projection+' FROM "'+table+'" t'+clause+' ORDER BY '+order
            if not keyset:sql+=' OFFSET '+str(offset)
            sql+=' LIMIT '+str(chunk_size)
            rows=read(table,'full_row_chunk',sql)
            if len(rows)!=min(chunk_size,total-offset)or any(not re.fullmatch('[0-9a-f]{32}',r.get('digest',''))for r in rows):
                raise ValueError('Incomplete protected chunk: '+table)
            for row in rows:
                if keyset:
                    key=row.get('native_key')
                    if (not isinstance(key,list)or len(key)!=len(names)
                            or any(type(v)is not int or not -(1<<63)<=v<(1<<63)for v in key)
                            or (cursor is not None and tuple(key)<=tuple(cursor))):
                        raise ValueError('Incomplete or unordered native protected keys: '+table)
                    cursor=key
                hasher.update((row['digest']+'\n').encode())
            offset+=len(rows); chunks+=1
            if progress:
                with Path(progress).open('a')as file:file.write(json.dumps({'table':table,'covered':offset,'total':total,'chunks':chunks,'statement_timeout_seconds':20})+'\n')
        if read(table,'final_count','SELECT COUNT(*) AS n FROM "'+table+'"')[0]['n']!=total:
            raise ValueError('Protected table changed during complete traversal: '+table)
        result[table]={'rows':total,'columns':[r['column_name']for r in columns],'key':names,'sha256':hasher.hexdigest()}
    return result


def protected_snapshot_session(site, progress=None, *, chunk_size=2048):
    """Same complete fingerprint, one bounded read-only process per snapshot."""
    from .gitlab_read_session import GitlabReadSession
    started = time.monotonic()
    session = GitlabReadSession(site)
    completed = False
    try:
        with session:
            result = protected_snapshot(site, progress, chunk_size=chunk_size, reader=session.select_rows)
        completed = True
        return result
    finally:
        # Append bounded timing to the existing progress stream; never record
        # SQL, returned values or a second copy of the fingerprint.
        if progress is not None:
            record = {'stage': 'protected_snapshot_session',
                      'status': 'complete' if completed else 'failed',
                      'seconds': time.monotonic() - started,
                      'queries': session.queries,
                      'query_seconds': sum(session.query_seconds),
                      'max_query_seconds': max(session.query_seconds, default=0.0),
                      'statement_timeout_seconds': 20}
            path = Path(progress)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a') as file:
                file.write(json.dumps(record, sort_keys=True) + '\n')


def auth_backup(site,username):
    if not isinstance(username,str)or not re.fullmatch('[A-Za-z0-9_.-]+',username): raise ValueError('Native benchmark username required')
    rows=select_rows(site,"SELECT id,"+','.join(AUTH_COLUMNS)+" FROM users WHERE username='"+username+"'")
    if len(rows)!=1: raise ValueError('Unique bound native account required')
    return rows[0]


def restore_auth_metadata(site,baseline):
    """Private environment reset of this bound user's pre-login native auth metadata only."""
    if set(baseline)!={'id',*AUTH_COLUMNS}or type(baseline['id'])is not int: raise ValueError('Exact private native auth baseline required')
    def literal(value):
        if value is None:return 'NULL'
        if type(value)is int:return str(value)
        if not isinstance(value,str):raise ValueError('Unsupported auth metadata type')
        return "'"+value.replace("'","''")+"'"
    sql='BEGIN;SET LOCAL statement_timeout=\'20s\';UPDATE users SET '+','.join('"'+key+'"='+literal(baseline[key])for key in AUTH_COLUMNS)+' WHERE id='+str(baseline['id'])+';COMMIT;'
    site.command(['/opt/gitlab/embedded/bin/psql','-h','/var/opt/gitlab/postgresql','-U','gitlab','-d','gitlabhq_production','-X','-q','-v','ON_ERROR_STOP=1','-c',sql],capture_output=True,text=True,timeout=40)


def terminal_judgment(received,reference,*,page_valid=True,runtime_error=False):
    if runtime_error or not isinstance(reference,dict):return {'status':'unknown','reward':None,'checks':{},'reason':'Native runtime/reference incomplete'}
    if not page_valid or received is None:return {'status':'failure','reward':0.0,'checks':{'actual_native_attachment':received is not None,'valid_task_page':page_valid}}
    return completion(received,reference)


def normalize_reference(reference,origin):
    result=json.loads(json.dumps(reference)); expected=urlsplit(origin)
    for row in result['rows']:
        value=urlsplit(row['URL'])
        if (value.scheme,value.netloc)!=(expected.scheme,expected.netloc):raise ValueError('Native record URL is outside actual local instance')
        row['URL']='local:'+value.path+('?' +value.query if value.query else '')
    return result


def consumer_ruby():
    native=(Path(__file__).with_name('gitlab_native_csv_consumer.rb')).read_text()
    return DELIVERY_ADAPTER_RUBY+'\n'+native


def native_command(site,args,*,seconds):
    """Private bounded consumer subprocess; kill the full Apptainer/Rails group on timeout."""
    if type(seconds)is not int or not 1<=seconds<=600:raise ValueError('Bounded native consumer seconds required')
    process=subprocess.Popen(site.base+args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    handlers={}
    def interrupted(signum,frame):
        raise SystemExit(128+signum)
    if threading.current_thread()is threading.main_thread():
        # The external source watchdog first sends SIGTERM. Give this narrow
        # new Rails process group a cleanup path before the supervisor's kill.
        for kind in (signal.SIGTERM,signal.SIGINT):handlers[kind]=signal.signal(kind,interrupted)
    try:
        stdout,stderr=process.communicate(timeout=seconds)
    except subprocess.TimeoutExpired as error:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        stdout,stderr=process.communicate(timeout=3)
        failed=subprocess.TimeoutExpired(args,seconds,output=stdout,stderr=stderr)
        from .native_failure_diagnostics import retain_private_failure
        retain_private_failure(site,failed)
        raise failed from error
    except BaseException:
        # An outer supervisor/signal may interrupt communicate before its own
        # timeout. The private Rails session must never outlive its source.
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.communicate(timeout=3)
        raise
    finally:
        for kind,handler in handlers.items():signal.signal(kind,handler)
    if process.returncode:
        failed=subprocess.CalledProcessError(process.returncode,args,output=stdout,stderr=stderr)
        from .native_failure_diagnostics import retain_private_failure
        retain_private_failure(site,failed)
        raise failed
    return subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
