"""Pinned native Magento startup programs; no task answer or external delivery."""

SEED = r"""
set -eu
[ -z "$(ls -A /state)" ]
cp -a /var/lib/mysql /state/mysql
cp -a /var/www/magento2/app/etc /state/etc
cp -a /var/www/magento2/generated /state/generated
cp /etc/nginx/fastcgi_params /state/fastcgi_params
mkdir -p /state/var/session /state/search/logs /state/search/tmp
cp -a /usr/share/java/elasticsearch/config /state/search/config
cp -a /usr/share/java/elasticsearch/data /state/search/data
chmod -R u+rwX /state/mysql /state/etc /state/generated /state/search
mkdir -p /state/tmp /state/var-tmp /state/mysql-tmp /state/redis /state/uploads /state/mail-outbox
mkdir -p /state/nginx/client /state/nginx/proxy /state/nginx/fastcgi
"""

CONFIGURE = r"""
$path='/var/www/magento2/app/etc/env.php';$e=include $path;
$e['db']['connection']['default']['host']='127.0.0.1:'.$argv[1];
unset($e['db']['connection']['default']['port']);
foreach($e['cache']['frontend'] as &$c){$c['backend_options']['server']='127.0.0.1';$c['backend_options']['port']=(int)$argv[2];}unset($c);
if(($e['session']['save']??'')==='redis'){$e['session']['redis']['host']='127.0.0.1';$e['session']['redis']['port']=(int)$argv[2];}
$e['system']['default']['system']['smtp']['transport']='sendmail';
$e['system']['default']['system']['smtp']['disable']='0';
$data="<?php\nreturn ".var_export($e,true).";\n";
if(file_put_contents($path,$data)!==strlen($data)||!chmod($path,0600))throw new RuntimeException('Private configuration incomplete');
$d=$e['db']['connection']['default'];
$p=new PDO('mysql:unix_socket=/runtime/mysql.sock;dbname='.$d['dbname'],$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$q=$p->prepare("UPDATE core_config_data SET value=? WHERE path IN ('web/unsecure/base_url','web/secure/base_url')");$q->execute(['http://127.0.0.1:'.$argv[3].'/']);
$q=$p->prepare("INSERT INTO core_config_data(scope,scope_id,path,value) VALUES('default',0,?,?) ON DUPLICATE KEY UPDATE value=VALUES(value)");
foreach(['opensearch','elasticsearch7','elasticsearch6','elasticsearch']as$engine){$q->execute(['catalog/search/'.$engine.'_server_hostname','127.0.0.1']);$q->execute(['catalog/search/'.$engine.'_server_port',$argv[4]]);}
echo 'configured';
"""

HEALTH = r"""
$ok=false;
try {
 if($argv[1]==='backend'){
  $e=include '/state/etc/env.php';$d=$e['db']['connection']['default'];
  $p=new PDO('mysql:unix_socket=/runtime/mysql.sock;dbname='.$d['dbname'],$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);$p->query('SELECT 1');
  $s=@fsockopen('127.0.0.1',(int)$argv[2],$no,$err,1);if(!$s)throw new RuntimeException('Redis pending');
  stream_set_timeout($s,1);fwrite($s,"*1\r\n$4\r\nPING\r\n");$pong=fgets($s);fclose($s);
  $ctx=stream_context_create(['http'=>['timeout'=>2,'follow_location'=>0]]);
  $raw=@file_get_contents('http://127.0.0.1:'.$argv[3].'/_cluster/health',false,$ctx);$health=$raw===false?null:json_decode($raw,true);
  $ok=$pong==="+PONG\r\n"&&is_array($health)&&in_array($health['status']??null,['green','yellow'],true);
 }elseif($argv[1]==='frontend'){
  if(count($argv)!==4||!is_numeric($argv[3])||!is_finite((float)$argv[3])||(float)$argv[3]<=0||(float)$argv[3]>86400)throw new RuntimeException('Invalid health budget');
  $ctx=stream_context_create(['http'=>['timeout'=>(float)$argv[3],'follow_location'=>0,'ignore_errors'=>true]]);
  $raw=@file_get_contents('http://127.0.0.1:'.$argv[2].'/customer/account/login/',false,$ctx);
  $ok=preg_match('/^HTTP\/[0-9.]+ 200/',$http_response_header[0]??'')&&$raw!==false&&strpos($raw,'customer-login')!==false&&strpos($raw,'id="email"')!==false;
 }else{throw new RuntimeException('Unsupported health phase');}
}catch(Throwable $error){$ok=false;}
echo $ok?'ready':'waiting';
"""

MAIL_SINK = r"""
$raw=stream_get_contents(STDIN,5000001);
if($raw===false||strlen($raw)>5000000)exit(65);
$path='/state/mail-outbox/'.bin2hex(random_bytes(16)).'.eml';
$s=fopen($path,'xb');if($s===false)exit(73);
if(!chmod($path,0600)||fwrite($s,$raw)!==strlen($raw)||!fflush($s))exit(74);
fclose($s);
"""
