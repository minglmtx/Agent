"""Exact stopped-state inventory and deletion; only fixed private roots accepted."""

INVENTORY = r"""
$root=$argv[1]??null;
if(!in_array($root,['/state','/snapshot/state'],true)||is_link($root)||!is_dir($root))throw new RuntimeException('Invalid private inventory root');
$rows=[];$files=0;$directories=0;$bytes=0;
$visit=function($path,$relative)use(&$visit,&$rows,&$files,&$directories,&$bytes){
 clearstatcache(true,$path);$s=lstat($path);if($s===false||is_link($path))throw new RuntimeException('Uncertain/symlink snapshot entry');
 $type=$s['mode']&0170000;$mode=$s['mode']&07777;
 if($type===0040000){$rows[]=[$relative,'directory',$mode];$directories++;$names=scandir($path);if($names===false)throw new RuntimeException('Unreadable private directory');
  foreach($names as$name){if($name==='.'||$name==='..')continue;$visit($path.'/'.$name,$relative===''?$name:$relative.'/'.$name);}
 }elseif($type===0100000&&$s['nlink']===1){$hash=hash_file('sha256',$path);if($hash===false)throw new RuntimeException('Unreadable private file');
  clearstatcache(true,$path);$after=lstat($path);if($after===false)throw new RuntimeException('Private file disappeared during inventory');
  foreach(['dev','ino','mode','nlink','uid','gid','size','mtime','ctime']as$key){if($s[$key]!==$after[$key])throw new RuntimeException('Private file changed during inventory');}
  $rows[]=[$relative,'file',$mode,$s['size'],$hash];$files++;$bytes+=$s['size'];
 }else{throw new RuntimeException('Special/hardlinked snapshot entry');}
};
$visit($root,'');
if(($argv[2]??'scan')==='clear'){
 if($root!=='/state')throw new RuntimeException('Snapshot is immutable');
 foreach($rows as$row){if($row[1]==='directory'&&!chmod($root.($row[0]===''?'':'/'.$row[0]),$row[2]|0700))throw new RuntimeException('Private directory permissions failed');}
 foreach(array_reverse($rows)as$row){if($row[0]==='')continue;$path=$root.'/'.$row[0];
  if($row[1]==='directory'){if(!chmod($path,$row[2]|0700)||!rmdir($path))throw new RuntimeException('Private directory deletion failed');}
  elseif(!unlink($path))throw new RuntimeException('Private file deletion failed');
 }
}elseif(($argv[2]??'scan')!=='scan'){throw new RuntimeException('Unknown inventory action');}
echo json_encode(['schema_version'=>'shopping-tree-inventory/1','sha256'=>hash('sha256',json_encode($rows,JSON_THROW_ON_ERROR)),'files'=>$files,'directories'=>$directories,'bytes'=>$bytes],JSON_THROW_ON_ERROR);
"""
