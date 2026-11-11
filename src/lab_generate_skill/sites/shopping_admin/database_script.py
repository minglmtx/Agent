"""Fixed native program, versioned with the Python package; no caller SQL/shell.

Full-database dump; private original Unix socket only. Failed/partial dump is
retained. Restore hashes and imports the same held regular file descriptor.
Credentials are passed only in the mysql child's environment, never argv/files.
"""

DATABASE_SNAPSHOT_PHP = r"""
$handle=null; $process=null; $pipes=[]; $failed=null; $cleanup=[]; $answer=null;
try {
    $mode=$argv[1]??'';
    if (!in_array($mode,['save','verify','restore'],true)) throw new RuntimeException('Invalid operation');
    foreach (['/state','/state/app','/state/app/app','/state/app/app/etc'] as $path) {
        if (is_link($path)||!is_dir($path)) throw new RuntimeException('Private state directory required');
    }
    $config='/state/app/app/etc/env.php'; $socket='/state/run/mysql.sock';
    if (is_link($config)||!is_file($config)||is_link($socket)||filetype($socket)!=='socket')
        throw new RuntimeException('Original private configuration/socket required');
    $env=include $config; $d=$env['db']['connection']['default'];
    foreach (['dbname','username','password'] as $key) {
        if (!isset($d[$key])||!is_string($d[$key])||strpos($d[$key],chr(0))!==false)
            throw new RuntimeException('Invalid private database configuration');
    }
    if (!preg_match('/^[A-Za-z0-9_]+$/D',$d['dbname'])) throw new RuntimeException('Unsupported database name');
    $dump='/state/framework-db-baseline.sql';
    if (is_link($dump)) throw new RuntimeException('Baseline cannot be a link');
    $handle=fopen($dump,$mode==='save'?'x+b':'rb');
    if ($handle===false) throw new RuntimeException('Baseline unavailable or already exists');
    $st=fstat($handle);
    if (($st['mode']&0170000)!==0100000||$st['nlink']!==1) throw new RuntimeException('Regular private baseline required');
    if ($mode==='save') {
        if (!chmod($dump,0600)) throw new RuntimeException('Baseline permissions failed');
        $cmd=['/usr/bin/mysqldump','--no-defaults','--socket='.$socket,
              '--user='.$d['username'],'--single-transaction','--skip-lock-tables','--hex-blob','--routines','--events',
              '--add-drop-database','--databases',$d['dbname']];
        $desc=[0=>['file','/dev/null','r'],1=>$handle,2=>['pipe','w']];
    } else {
        $expected=$argv[2]??''; $size=$argv[3]??'';
        if (!preg_match('/^[0-9a-f]{64}$/D',$expected)||!ctype_digit($size)||(int)$size<100)
            throw new RuntimeException('Explicit original baseline pin required');
        $hash=hash_init('sha256');hash_update_stream($hash,$handle);$actual=hash_final($hash);
        if ($actual!==$expected||$st['size']!==(int)$size) throw new RuntimeException('Original baseline changed');
        if (!rewind($handle)) throw new RuntimeException('Baseline rewind failed');
        $cmd=['/usr/bin/mysql','--no-defaults','--socket='.$socket,'--user='.$d['username'],$d['dbname']];
        $desc=[0=>$handle,1=>['file','/dev/null','w'],2=>['pipe','w']];
    }
    if ($mode!=='verify') {
    $process=proc_open($cmd,$desc,$pipes,null,['MYSQL_PWD'=>$d['password'],'PATH'=>'/usr/bin:/bin','LANG'=>'C']);
    if (!is_resource($process)) throw new RuntimeException('Database client failed to start');
    $stderr=stream_get_contents($pipes[2],65536); fclose($pipes[2]); $pipes=[];
    $status=proc_close($process);$process=null;
    if ($status!==0) {
        if (is_string($stderr)) fwrite(STDERR,$stderr);
        throw new RuntimeException('Database client exit '.$status);
    }
    }
    if (!fflush($handle)) throw new RuntimeException('Baseline stream flush failed');
    if ($mode==='save' && function_exists('fsync') && !fsync($handle)) throw new RuntimeException('Baseline sync failed');
    if (!rewind($handle)) throw new RuntimeException('Baseline rewind failed');
    $hash=hash_init('sha256');hash_update_stream($hash,$handle);$digest=hash_final($hash);$after=fstat($handle);
    if ($after['size']<100) throw new RuntimeException('Empty database dump');
    if ($mode!=='save'&&($digest!==$expected||$after['size']!==(int)$size))
        throw new RuntimeException('Baseline changed during import');
    $answer=['schema_version'=>'admin-database-reply/2','operation'=>$mode,'size_bytes'=>$after['size'],'sha256'=>$digest];
} catch (Throwable $e) { $failed=get_class($e).': '.$e->getMessage(); }
finally {
    foreach ($pipes as $pipe) if (is_resource($pipe)&&!fclose($pipe)) $cleanup[]='pipe close failed';
    if (is_resource($process)) { $status=proc_close($process); if ($status!==0) $cleanup[]='client close failed'; }
    if (is_resource($handle)&&!fclose($handle)) $cleanup[]='baseline close failed';
}
if ($failed!==null||$cleanup) {
    fwrite(STDERR,json_encode(['primary'=>$failed,'cleanup'=>$cleanup])."\n");exit(2);
}
echo json_encode($answer,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
"""
