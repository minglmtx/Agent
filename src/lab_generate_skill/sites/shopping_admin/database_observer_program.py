"""Authorized PROCESS observation for a fresh private MySQL copy only.

The startup statements select exactly one existing application account. No new
account, password, write privilege or shared image is modified. The init file
contains the account name, never its credential. Missing/ambiguous accounts do
not produce a GRANT; the mandatory post-start visibility check must still pass.

The pinned image runs MariaDB 10.6: read account identity from global_priv.
Its legacy mysql.user view has a missing mariadb.sys definer. Do not repair
that account/view or edit privilege rows; GRANT remains the only mutation.
"""

DATABASE_OBSERVER_INIT_PHP = r"""
$f=null;$primary=null;$cleanup=null;
try {
 foreach(['/state','/state/app','/state/app/app','/state/app/app/etc'] as $path){if(is_link($path)||!is_dir($path))throw new RuntimeException('Private state directory required');}
 $file='/state/app/app/etc/env.php';if(is_link($file)||!is_file($file))throw new RuntimeException('Original private DB configuration required');
 $e=include $file;$user=$e['db']['connection']['default']['username']??null;
 if(!is_string($user)||!preg_match('/^[A-Za-z0-9_]{1,32}$/D',$user)||strtolower($user)==='root')throw new RuntimeException('Unsupported private application database account');
 $sql="SET @lab_observer_account = (SELECT CONCAT(QUOTE(User),'@',QUOTE(Host)) FROM mysql.global_priv WHERE User = '".$user."');\n"
     ."SET @lab_observer_grant = CONCAT('GRANT PROCESS ON *.* TO ',@lab_observer_account);\n"
     ."PREPARE lab_observer_stmt FROM @lab_observer_grant;\nEXECUTE lab_observer_stmt;\nDEALLOCATE PREPARE lab_observer_stmt;\n";
 umask(0077);$f=fopen('/state/database-observer-init.sql','xb');
 if($f===false)throw new RuntimeException('Observer initialization already exists or unavailable');
 if(fwrite($f,$sql)!==strlen($sql)||!fflush($f))throw new RuntimeException('Observer initialization incomplete');
}catch(Throwable $e){$primary=get_class($e).': '.$e->getMessage();}
finally{if(is_resource($f)){try{if(!fclose($f))throw new RuntimeException('Observer initialization close failed');}catch(Throwable $e){$cleanup=get_class($e).': '.$e->getMessage();}}}
if($primary!==null||$cleanup!==null){fwrite(STDERR,json_encode(['primary'=>$primary,'cleanup'=>$cleanup],JSON_THROW_ON_ERROR).PHP_EOL);exit(2);}
echo 'observer-configured';
"""
