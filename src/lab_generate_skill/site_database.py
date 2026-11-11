"""Private, bounded read-only database access for site evaluators, never actor tools."""
import json
import re


class DatabaseReadError(RuntimeError):
    """Diagnostics without SQL, query values, connection details or stderr."""
    def __init__(self, output):
        match = re.search(r'SQLSTATE\[([0-9A-Z]{5})\].*?:\s*(\d{3,5})\b', output)
        self.sqlstate = match[1] if match else None
        self.driver_code = int(match[2]) if match else None
        self.failure_kind = 'memory_exhausted' if 'LAB_DB_MEMORY_EXHAUSTED' in output else None
        marker = re.search(r'LAB_DB_ERROR (\{[^\n]*\})', output)
        if marker:
            try:
                details = json.loads(marker[1])
                state, code = details.get('sqlstate'), details.get('driver_code')
                self.sqlstate = state if isinstance(state, str) and re.fullmatch(r'[0-9A-Z]{5}', state) else None
                self.driver_code = code if type(code) is int and 100 <= code <= 99999 else None
            except (ValueError, AttributeError):
                pass
        super().__init__('Read-only database query failed')


def select_rows(site, sql, *, stream=False):
    if not isinstance(sql, str) or not sql.lstrip().upper().startswith('SELECT '):
        raise ValueError('Only SELECT references are supported')
    if site.domain == 'shopping':
        code = r'''$reserve=str_repeat(' ',32768);
register_shutdown_function(function() use (&$reserve) {$reserve=null;$e=error_get_last();
if ($e && $e['type']===E_ERROR && strpos($e['message'],'Allowed memory size')!==false) fwrite(STDERR,"LAB_DB_MEMORY_EXHAUSTED\n");});
try {$e=include '/var/www/magento2/app/etc/env.php';$d=$e['db']['connection']['default'];$h=explode(':',$d['host']);
$p=new PDO('mysql:host='.$h[0].';port='.$h[1].';dbname='.$d['dbname'],$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_EMULATE_PREPARES=>false]);
if ($argv[2]==='stream') $p->setAttribute(PDO::MYSQL_ATTR_USE_BUFFERED_QUERY,false);
$p->exec('START TRANSACTION READ ONLY');
$q=$p->prepare($argv[1]);$q->execute();
if ($argv[2]==='stream') {echo '[';$sep='';while ($row=$q->fetch(PDO::FETCH_ASSOC)) {echo $sep,json_encode($row);$sep=',';}echo ']';}
else {echo json_encode($q->fetchAll(PDO::FETCH_ASSOC));}
$p->exec('ROLLBACK');
} catch (PDOException $e) {
  $i=$e->errorInfo; fwrite(STDERR,'LAB_DB_ERROR '.json_encode(['sqlstate'=>$i[0]??null,'driver_code'=>isset($i[1])?(int)$i[1]:null])."\n"); exit(42);
}'''
        try:
            data=site.command(['php', '-r', code, sql, 'stream' if stream else 'buffered'], capture_output=True, text=True, timeout=40).stdout
        except __import__('subprocess').CalledProcessError as exc:
            raise DatabaseReadError((exc.stderr or '') + '\n' + (exc.stdout or '')) from None
        return json.loads(data)
    prefix = (['psql','-h','/state/run','-p',str(site.db_port),'-U','postmill','-d','postmill']
              if site.domain == 'reddit' else
              ['/opt/gitlab/embedded/bin/psql','-h','/var/opt/gitlab/postgresql','-U','gitlab','-d','gitlabhq_production'])
    statement = "SELECT COALESCE(json_agg(q),'[]'::json) FROM (" + sql + ") q"
    data = site.command(prefix+['-X','-q','-A','-t','-v','ON_ERROR_STOP=1','-c','BEGIN READ ONLY','-c',"SET LOCAL statement_timeout='20s'",'-c',statement,'-c','ROLLBACK'],capture_output=True,text=True,timeout=40).stdout
    return json.loads(data)
