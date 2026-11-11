"""Fixed private-instance programs, published with source; no dynamic script paths."""

SEED = r"""
set -eu
[ -z "$(ls -A /state)" ]
cp -a /var/lib/mysql /state/mysql
cp -a /var/www/magento2 /state/app
chmod -R u+rwX /state/mysql /state/app
mkdir -p /state/run /state/redis /state/nginx /state/php-upload
cp /etc/nginx/fastcgi_params /state/fastcgi_params
mkdir -p /state/elasticsearch/logs /state/elasticsearch/tmp
cp -a /usr/share/java/elasticsearch/config /state/elasticsearch/config
cp -a /usr/share/java/elasticsearch/data /state/elasticsearch/data
chmod -R u+rwX /state/elasticsearch
"""

CONFIGURE = r"""
$path='/var/www/magento2/app/etc/env.php';$e=include $path;
$e['db']['connection']['default']['host']='127.0.0.1:'.$argv[1];
unset($e['db']['connection']['default']['port']);
foreach ($e['cache']['frontend'] as &$c) {
 $c['backend_options']['server']='127.0.0.1';
 $c['backend_options']['port']=(int)$argv[2];
}
unset($c);
$data="<?php\nreturn ".var_export($e,true).";\n";
if (file_put_contents($path,$data)!==strlen($data) || !chmod($path,0600)) throw new RuntimeException('Private configuration write failed');
$d=$e['db']['connection']['default'];
$p=new PDO('mysql:unix_socket=/state/run/mysql.sock;dbname='.$d['dbname'],$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$q=$p->prepare("UPDATE core_config_data SET value=? WHERE path IN ('web/unsecure/base_url','web/secure/base_url')");
$q->execute(['http://127.0.0.1:'.$argv[3].'/']);
$p->exec("UPDATE core_config_data SET value='0' WHERE path IN ('admin/security/password_is_forced','admin/security/password_lifetime')");
$q=$p->prepare("INSERT INTO core_config_data(scope,scope_id,path,value) VALUES('default',0,?,?) ON DUPLICATE KEY UPDATE value=VALUES(value)");
foreach (['opensearch','elasticsearch7','elasticsearch6','elasticsearch'] as $engine) {
 $q->execute(['catalog/search/'.$engine.'_server_hostname','127.0.0.1']);
 $q->execute(['catalog/search/'.$engine.'_server_port',$argv[4]]);
}
echo 'configured';
"""

HEALTH = r"""
$ok=false;$until=null;
if (($argv[1]??null)==='frontend') {
 if (count($argv)!==4 || !is_numeric($argv[3]) || !is_finite((float)$argv[3]) || (float)$argv[3]<=0 || (float)$argv[3]>86400) {fwrite(STDERR, 'Invalid frontend health budget'.PHP_EOL);exit(64);}
 $until=hrtime(true)/1e9+(float)$argv[3];
}
try {
 if ($argv[1]==='backend') {
  $e=include '/state/app/app/etc/env.php';$d=$e['db']['connection']['default'];
  $p=new PDO('mysql:unix_socket=/state/run/mysql.sock;dbname='.$d['dbname'],$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
  $p->query('SELECT 1');
  $s=@fsockopen('127.0.0.1',(int)$argv[2],$errno,$errstr,1);
  if (!$s) throw new RuntimeException('Redis not ready');
  stream_set_timeout($s,1);fwrite($s,"*1\r\n$4\r\nPING\r\n");$pong=fgets($s);fclose($s);
  $ctx=stream_context_create(['http'=>['timeout'=>2,'follow_location'=>0]]);
  $raw=@file_get_contents('http://127.0.0.1:'.$argv[3].'/_cluster/health',false,$ctx);
  $health=$raw===false ? null : json_decode($raw,true);
  $ok=$pong==="+PONG\r\n" && is_array($health) && in_array($health['status']??null,['green','yellow'],true);
 } elseif ($argv[1]==='frontend') {
  $origin='http://127.0.0.1:'.$argv[2];$path='/admin';
  for ($i=0;$i<5;$i++) {
   $remaining=$until-hrtime(true)/1e9;
   if ($remaining<=0) break;
   $ctx=stream_context_create(['http'=>['timeout'=>$remaining,'follow_location'=>0,'ignore_errors'=>true]]);
   $raw=@file_get_contents($origin.$path,false,$ctx);
   $status=$http_response_header[0]??'';
   if (preg_match('/^HTTP\/[0-9.]+ 200/', $status)) {
    $ok=$raw!==false && (stripos($raw,'login')!==false || stripos($raw,'sign in')!==false);break;
   }
   if (!preg_match('/^HTTP\/[0-9.]+ 30[12378]/',$status)) break;
   $location=null;
   foreach ($http_response_header??[] as $header) {if (stripos($header,'Location:')===0) $location=trim(substr($header,9));}
   if (!is_string($location)) break;
   if (strpos($location,$origin.'/')===0) $location=substr($location,strlen($origin));
   if (substr($location,0,1)!=='/' || substr($location,0,2)==='//') break;
   $path=$location;
  }
 } else {throw new RuntimeException('Unsupported health mode');}
} catch (Throwable $error) {$ok=false;}
echo $ok ? 'ready' : 'waiting';
"""

MAIL_SINK = r"""<?php
$directory='/var/www/magento2/var/training-mail';
if (!is_dir('/state/app') || !is_dir('/state/mysql')) exit(71);
if (!is_dir($directory) && !mkdir($directory,0700,true)) exit(73);
if (is_link($directory)) exit(73);
$raw=stream_get_contents(STDIN,5000001);
if ($raw===false || strlen($raw)>5000000) exit(65);
$filename=$directory.'/'.bin2hex(random_bytes(16)).'.eml';
if (file_put_contents($filename,$raw,LOCK_EX)!==strlen($raw)) exit(74);
chmod($filename,0600);
"""
