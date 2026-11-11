"""Coherent native tree bytes, paths, modes and ownership; fixed roots only."""

INVENTORY = r"""
$root=$argv[1]??null;$action=$argv[2]??'scan';
if(!in_array($root,['/state','/snapshot/state'],true)||is_link($root)||!is_dir($root))throw new RuntimeException('Invalid private Postmill inventory root');
if(!in_array($action,['scan','clear'],true)||($action==='clear'&&$root!=='/state'))throw new RuntimeException('Unknown inventory action or immutable snapshot');
$rows=[];$files=0;$directories=0;$bytes=0;
$visit=function($path,$relative)use(&$visit,&$rows,&$files,&$directories,&$bytes){
 clearstatcache(true,$path);$s=lstat($path);
 if($s===false||is_link($path)||count($rows)>=1000000)throw new RuntimeException('Uncertain/symlink/oversized native snapshot tree');
 $type=$s['mode']&0170000;$mode=$s['mode']&07777;
 if($type===0040000){
  $rows[]=[$relative,'directory',$mode,$s['uid'],$s['gid']];$directories++;
  $names=scandir($path);if($names===false)throw new RuntimeException('Unreadable native directory');
  foreach($names as$name){if($name==='.'||$name==='..')continue;$visit($path.'/'.$name,$relative===''?$name:$relative.'/'.$name);}
 }elseif($type===0100000&&$s['nlink']===1){
  $hash=hash_file('sha256',$path);if($hash===false)throw new RuntimeException('Unreadable native file');
  clearstatcache(true,$path);$after=lstat($path);if($after===false)throw new RuntimeException('Native file disappeared');
  foreach(['dev','ino','mode','nlink','uid','gid','size','mtime','ctime']as$key){if($s[$key]!==$after[$key])throw new RuntimeException('Native file changed during inventory');}
  $rows[]=[$relative,'file',$mode,$s['uid'],$s['gid'],$s['size'],$hash];$files++;$bytes+=$s['size'];
 }else{throw new RuntimeException('Special/hardlinked native snapshot entry');}
};
$visit($root,'');
if($action==='clear'){
 // Validate the complete tree before deleting anything; no links are followed.
 foreach($rows as$row){if($row[1]==='directory'&&!chmod($root.($row[0]===''?'':'/'.$row[0]),$row[2]|0700))throw new RuntimeException('Native directory permissions failed');}
 foreach(array_reverse($rows)as$row){if($row[0]==='')continue;$path=$root.'/'.$row[0];
  if($row[1]==='directory'){if(!rmdir($path))throw new RuntimeException('Native directory removal failed');}
  elseif(!unlink($path))throw new RuntimeException('Native file removal failed');
 }
}
echo json_encode(['schema_version'=>'reddit-tree-inventory/1','sha256'=>hash('sha256',json_encode($rows,JSON_THROW_ON_ERROR)),'files'=>$files,'directories'=>$directories,'bytes'=>$bytes],JSON_THROW_ON_ERROR);
"""
