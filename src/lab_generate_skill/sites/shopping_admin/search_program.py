"""Fixed bounded local snapshot API; no caller URL, repository, index or scripts."""

from .search_http_program import SEARCH_HTTP_PHP

SEARCH_SNAPSHOT_PHP = (
    r"""
$stage='input';$deleted=[];$attempted=[];$deletedStreams=[];$attemptedStreams=[];
try {
 if(count($argv)!==5||!ctype_digit($argv[1])||(int)$argv[1]<1024||(int)$argv[1]>65535||!is_numeric($argv[2])||!is_finite((float)$argv[2])||(float)$argv[2]<=0||(float)$argv[2]>86400) throw new RuntimeException('Invalid original port/budget');
 $port=(int)$argv[1];$until=hrtime(true)/1e9+(float)$argv[2];$mode=$argv[3];
 if(!in_array($mode,['save','verify','preflight','restore'],true))throw new RuntimeException('Unsupported search operation');
 $expected=json_decode($argv[4],true,32,JSON_THROW_ON_ERROR);
 if(($mode==='save'&&$expected!==null)||($mode!=='save'&&!is_array($expected)))throw new RuntimeException('Expected original snapshot descriptor');
"""
    + SEARCH_HTTP_PHP
    + r"""
 function names($items){
  if(!is_array($items)||count($items)>256)throw new RuntimeException('Invalid index inventory');$names=[];
  foreach($items as $name){if(!is_string($name)||!preg_match('/^[a-z0-9.][a-z0-9_.-]{0,254}$/D',$name)||in_array($name,['.','..'],true))throw new RuntimeException('Not literal index name');$names[]=$name;}
  if(count(array_unique($names))!==count($names))throw new RuntimeException('Duplicate indices');sort($names,SORT_STRING);return $names;
 }
 function inventory(){
  $rows=request('GET','/_cat/indices?format=json&expand_wildcards=all&h=index,status');$n=[];
  foreach($rows as $row){if(!is_array($row)||($row['status']??null)!=='open')throw new RuntimeException('All original indices must be open');$n[]=$row['index']??null;}return names($n);
 }
 function streams($indices){
  $rows=request('GET','/_data_stream?expand_wildcards=all')['data_streams']??null;
  if(!is_array($rows)||count($rows)>256)throw new RuntimeException('Invalid data stream inventory');
  $result=[];$backing=[];$streamNames=[];
  foreach($rows as $row){
   if(!is_array($row)||!is_array($row['indices']??null)||count($row['indices'])===0)throw new RuntimeException('Invalid data stream backing indices');
   $streamNames[]=$row['name']??null;$members=[];
   foreach($row['indices'] as $index){$members[]=$index['index_name']??null;}
   $members=names($members);foreach($members as $member){if(!in_array($member,$indices,true)||in_array($member,$backing,true))throw new RuntimeException('Changed or duplicate stream backing identity');$backing[]=$member;}
   names([$row['name']??null]);$result[$row['name']]=$members;
  }
  names($streamNames);ksort($result,SORT_STRING);return [$result,names($backing)];
 }
 function stopped($wait=false){
  global $until;
  do{
   $mode=request('GET','/_ilm/status')['operation_mode']??null;
   if($mode==='STOPPED')return;
   if($mode!=='STOPPING'||!$wait)throw new RuntimeException('ILM is not stopped');
   $remaining=$until-hrtime(true)/1e9;if($remaining<=0)throw new RuntimeException('ILM stop deadline expired');
   usleep((int)(min(0.1,$remaining)*1e6));
  }while(true);
 }
 function identity(){
  $info=request('GET','/');$uuid=$info['cluster_uuid']??null;$version=$info['version']['number']??null;
  if(!is_string($uuid)||!preg_match('/^[A-Za-z0-9_-]{1,128}$/D',$uuid)||!is_string($version)||!preg_match('/^7\.[0-9]+\.[0-9]+$/D',$version))throw new RuntimeException('Unsupported original search identity/version');return [$uuid,$version];
 }
 function snapshot($s,$id){
  if(!is_array($s)||($s['snapshot']??null)!=='baseline'||($s['state']??null)!=='SUCCESS'||($s['include_global_state']??null)!==true||($s['failures']??null)!==[])throw new RuntimeException('Snapshot not fully successful');
  $uuid=$s['uuid']??null;$v=$s['version']??null;$sh=$s['shards']??null;
  if(!is_string($uuid)||!preg_match('/^[A-Za-z0-9_-]{1,128}$/D',$uuid)||$v!==$id[1]||!is_array($sh)||!is_int($sh['total']??null)||$sh['total']<0||($sh['successful']??null)!==$sh['total']||($sh['failed']??null)!==0)throw new RuntimeException('Incomplete original snapshot shards');
  return ['cluster_uuid'=>$id[0],'version'=>$id[1],'repository'=>'lab_admin_recovery','snapshot'=>'baseline','snapshot_uuid'=>$uuid,'indices'=>names($s['indices']??null),'data_streams'=>names($s['data_streams']??null),'shards'=>$sh['total']];
 }
 function acknowledged($reply){if(($reply['acknowledged']??null)!==true)throw new RuntimeException('Mutation not acknowledged');}
 $id=identity();$repo='/_snapshot/lab_admin_recovery';$path=$repo.'/baseline';
 if($mode==='save'){
  $stage='stop_ilm';acknowledged(request('POST','/_ilm/stop'));stopped(true);
  $stage='save_preflight';$before=inventory();[$beforeStreams,$backing]=streams($before);
  $dir='/state/elasticsearch/snapshots';if(is_link($dir)||!is_dir($dir)||count(scandir($dir))!==2)throw new RuntimeException('Fresh private repository directory required');
  if(request('GET',$repo,null,true)!==null)throw new RuntimeException('Original repository already exists');
  $stage='register_repository';acknowledged(request('PUT',$repo,['type'=>'fs','settings'=>['location'=>$dir,'compress'=>true]]));
  $stage='save_snapshot';$r=request('PUT',$path.'?wait_for_completion=true',['include_global_state'=>true,'partial'=>false,'ignore_unavailable'=>false]);
  $record=snapshot($r['snapshot']??null,$id);
  stopped();if($record['indices']!==$before||$record['data_streams']!==array_keys($beforeStreams)||inventory()!==$before||streams($before)[0]!==$beforeStreams||identity()!==$id)throw new RuntimeException('Index or stream inventory changed during save');
  $out=['schema_version'=>'admin-search-reply/2','operation'=>'save','snapshot'=>$record];
 }else{
  $stage='verify_repository';$repos=request('GET',$repo);$r=$repos['lab_admin_recovery']??null;
  if(!is_array($r)||($r['type']??null)!=='fs'||($r['settings']['location']??null)!=='/state/elasticsearch/snapshots')throw new RuntimeException('Original repository was replaced');
  $stage='verify_snapshot';$r=request('GET',$path);$ss=$r['snapshots']??null;
  if(!is_array($ss)||count($ss)!==1)throw new RuntimeException('Original snapshot not unique');$record=snapshot($ss[0],$id);
  if($record!==$expected)throw new RuntimeException('Original snapshot identity changed');
  if($mode==='verify'){$out=['schema_version'=>'admin-search-reply/2','operation'=>'verify','snapshot'=>$record];}
  else{
   $stage='restore_preflight';stopped();$current=inventory();[$currentStreams,$backing]=streams($current);
   if($mode==='preflight'){echo json_encode(['schema_version'=>'admin-search-reply/2','operation'=>'preflight','snapshot'=>$record],JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);exit(0);}
   $stage='delete_current_streams';
   foreach(array_keys($currentStreams) as $name){if(identity()!==$id)throw new RuntimeException('Original cluster changed');$attemptedStreams[]=$name;acknowledged(request('DELETE','/_data_stream/'.rawurlencode($name)));$deletedStreams[]=$name;}
   $standalone=array_values(array_diff($current,$backing));
   if(inventory()!==$standalone)throw new RuntimeException('Unexpected index change after deleting streams');
   $stage='delete_current_indices';
   foreach($standalone as $name){if(identity()!==$id)throw new RuntimeException('Original cluster changed');$attempted[]=$name;acknowledged(request('DELETE','/'.rawurlencode($name)));$deleted[]=$name;}
   $stage='restore_snapshot';$r=request('POST',$path.'/_restore?wait_for_completion=true',['include_global_state'=>true,'include_aliases'=>true,'partial'=>false,'ignore_unavailable'=>false]);$sh=$r['snapshot']['shards']??null;
   if(!is_array($sh)||($sh['total']??null)!==$record['shards']||($sh['successful']??null)!==$record['shards']||($sh['failed']??null)!==0)throw new RuntimeException('Restore shards incomplete');
   $stage='verify_restored';$remaining=max(1,(int)(1000*($until-hrtime(true)/1e9)));
   $h=request('GET','/_cluster/health?wait_for_status=yellow&timeout='.$remaining.'ms');
   if(($h['timed_out']??null)!==false||!in_array($h['status']??null,['green','yellow'],true)||identity()!==$id||inventory()!==$record['indices']||array_keys(streams($record['indices'])[0])!==$record['data_streams'])throw new RuntimeException('Original restored cluster not ready or inventory differs');
   stopped();
   $out=['schema_version'=>'admin-search-reply/2','operation'=>'restore','snapshot'=>$record,'health'=>$h['status'],'successful_shards'=>$sh['successful']];
  }
 }
 echo json_encode($out,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
}catch(Throwable $e){fwrite(STDERR,json_encode(['stage'=>$stage,'attempted_stream_deletions'=>$attemptedStreams,'deleted_streams'=>$deletedStreams,'attempted_deletions'=>$attempted,'deleted_indices'=>$deleted,'error'=>get_class($e),'message'=>$e->getMessage()],JSON_UNESCAPED_SLASHES).PHP_EOL);exit(2);}
"""
)
