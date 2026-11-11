"""Read original backend activity only; errors are not busy/retry signals."""

from .search_http_program import SEARCH_HTTP_PHP

DATABASE_DRAIN_PHP = r"""
try {
 $file='/state/app/app/etc/env.php';$socket='/state/run/mysql.sock';
 if(is_link($file)||!is_file($file)||is_link($socket)||filetype($socket)!=='socket')throw new RuntimeException('Original private DB files required');
 foreach (['/state','/state/app','/state/app/app','/state/app/app/etc'] as $path) {
  if(is_link($path)||!is_dir($path))throw new RuntimeException('Private state directory required');
 }
 $e=include $file;$d=$e['db']['connection']['default'];
 foreach (['dbname','username','password'] as $key) {
  if(!isset($d[$key])||!is_string($d[$key])||strpos($d[$key],chr(0))!==false)throw new RuntimeException('Invalid private database configuration');
 }
 if(!preg_match('/^[A-Za-z0-9_]+$/D',$d['dbname']))throw new RuntimeException('Unsupported database name');
 $p=new PDO('mysql:unix_socket='.$socket.';dbname='.$d['dbname'],$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
 $grantee=$p->query("SELECT CONCAT(QUOTE(SUBSTRING_INDEX(CURRENT_USER(),'@',1)), '@', QUOTE(SUBSTRING_INDEX(CURRENT_USER(),'@',-1)))")->fetchColumn();
 $q=$p->prepare("SELECT COUNT(*) FROM information_schema.USER_PRIVILEGES WHERE GRANTEE=? AND PRIVILEGE_TYPE='PROCESS'");$q->execute([$grantee]);
 if((string)$q->fetchColumn()!=='1')throw new RuntimeException('Complete SQL process visibility required');
 function number($v){if(!(is_int($v)||(is_string($v)&&ctype_digit($v)))||(int)$v<0||(int)$v>1000000)throw new RuntimeException('Invalid SQL activity count');return (int)$v;}
 if(strtoupper((string)$p->query('SELECT @@event_scheduler')->fetchColumn())!=='OFF')throw new RuntimeException('Uncontrolled database event scheduler');
 $connections=number($p->query('SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE ID<>CONNECTION_ID()')->fetchColumn());
 $transactions=number($p->query('SELECT COUNT(*) FROM information_schema.INNODB_TRX')->fetchColumn());
 echo json_encode(['other_sql_connections'=>$connections,'sql_transactions'=>$transactions],JSON_THROW_ON_ERROR);
}catch(Throwable $e){fwrite(STDERR,get_class($e).': '.$e->getMessage().PHP_EOL);exit(2);}
"""

SEARCH_DRAIN_PHP = (
    r"""
try {
 if(count($argv)!==3||!ctype_digit($argv[1])||(int)$argv[1]<1024||(int)$argv[1]>65535||!is_numeric($argv[2])||!is_finite((float)$argv[2])||(float)$argv[2]<=0||(float)$argv[2]>86400)throw new RuntimeException('Invalid original search port/budget');
 $port=(int)$argv[1];$until=hrtime(true)/1e9+(float)$argv[2];
"""
    + SEARCH_HTTP_PHP
    + r"""
 $r=request('GET','/_tasks?actions=indices:data/write/*,indices:admin/*');
 $nodes=$r['nodes']??null;if(!is_array($nodes))throw new RuntimeException('Missing search task inventory');
 foreach(['node_failures','task_failures'] as $key){if(array_key_exists($key,$r)&&(!is_array($r[$key])||count($r[$key])!==0))throw new RuntimeException('Search task observation incomplete');}
 $count=0;foreach($nodes as $node){$tasks=$node['tasks']??null;if(!is_array($tasks))throw new RuntimeException('Missing node tasks');$count+=count($tasks);}
 if($count>4096)throw new RuntimeException('Search tasks outside bound');
 echo json_encode(['search_write_tasks'=>$count],JSON_THROW_ON_ERROR);
}catch(Throwable $e){fwrite(STDERR,get_class($e).': '.$e->getMessage().PHP_EOL);exit(2);}
"""
)
