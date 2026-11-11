"""Fixed read-only content measurement against the original local snapshot.

Scroll contexts are bounded and cleared; no caller SQL, URL, index selector or
script enters this command. Any incomplete read or changed identity fails.
"""

from .navigation_database_projection_program import DATABASE_PROJECTION_PHP
from .navigation_search_projection_program import (
    SEARCH_EQUIVALENCE_PHP,
    SEARCH_METADATA_NORMALIZATION_PHP,
)

NAVIGATION_CONTENTS_PHP = (
    DATABASE_PROJECTION_PHP
    + SEARCH_METADATA_NORMALIZATION_PHP
    + SEARCH_EQUIVALENCE_PHP
    + r"""
$scroll=null;$file=null;$until=0;$port=0;$failed=null;$answer=null;
try {
 if(count($argv)!==7||!ctype_digit($argv[1])||(int)$argv[1]<1024||(int)$argv[1]>65535||!is_numeric($argv[2])||!is_finite((float)$argv[2])||(float)$argv[2]<=0||(float)$argv[2]>86400||!preg_match('/^[0-9a-f]{64}$/D',$argv[3])||!ctype_digit($argv[4]))throw new RuntimeException('Invalid measured snapshot/budget');
 $port=(int)$argv[1];$until=hrtime(true)/1e9+(float)$argv[2];
 $expected=json_decode($argv[5],false,64,JSON_THROW_ON_ERROR);
 if(!is_object($expected)||!is_array($expected->indices??null)||!is_string($expected->snapshot_uuid??null))throw new RuntimeException('Original search snapshot required');
 function canonical($v){if(is_object($v)){$a=get_object_vars($v);ksort($a,SORT_STRING);$r=new stdClass();foreach($a as $k=>$x)$r->$k=canonical($x);return $r;}if(is_array($v))return array_map('canonical',$v);return $v;}
 function bytes($v){return json_encode(canonical($v),JSON_UNESCAPED_SLASHES|JSON_PRESERVE_ZERO_FRACTION|JSON_THROW_ON_ERROR);}
 function digest($v){return hash('sha256',bytes($v));}
 function request($method,$path,$body=null,$rawSource=false){
  global $port,$until;$remaining=$until-hrtime(true)/1e9;if($remaining<=0)throw new RuntimeException('Content read deadline expired');
  $opts=['method'=>$method,'timeout'=>$remaining,'follow_location'=>0,'ignore_errors'=>true,'header'=>"Content-Type: application/json\r\nConnection: close\r\n"];
  if($body!==null)$opts['content']=bytes($body);
  $s=@fopen('http://127.0.0.1:'.$port.$path,'rb',false,stream_context_create(['http'=>$opts]));$headers=$http_response_header??[];
  if($s===false)throw new RuntimeException('Content HTTP failed');
  try{$raw=stream_get_contents($s,16777217);$meta=stream_get_meta_data($s);}finally{fclose($s);}
  if($raw===false||strlen($raw)>16777216||($meta['timed_out']??true)!==false||($meta['eof']??false)!==true||!preg_match('/^HTTP\/[0-9.]+ 200(?: |$)/',$headers[0]??''))throw new RuntimeException('Incomplete content HTTP');
  if($path==='/_cluster/state/metadata'){
   // Metadata numbers must be exactly representable. Unusual numeric template
   // parameters stay unsupported instead of silently rounding into equality.
   $quoted=false;$escaped=false;$outside='';
   for($j=0;$j<strlen($raw);$j++){$c=$raw[$j];if($quoted){if($escaped)$escaped=false;elseif($c==='\\')$escaped=true;elseif($c==='"')$quoted=false;}else{if($c==='"'){$quoted=true;$outside.=' ';}else $outside.=$c;}}
   preg_match_all('/-?[0-9][0-9.eE+\-]*/',$outside,$numbers);foreach($numbers[0] as $n)if(!preg_match('/^-?(0|[1-9][0-9]{0,14})$/D',$n))throw new RuntimeException('Unsupported exact metadata numeric value');
  }
  $v=json_decode($raw,false,128,JSON_THROW_ON_ERROR);if(!is_object($v))throw new RuntimeException('Content JSON object required');return $rawSource?$raw:$v;
 }
 function identity(){global $expected;
  $id=request('GET','/');$snap=request('GET','/_snapshot/lab_admin_recovery/baseline');$all=$snap->snapshots??null;
  if(($id->cluster_uuid??null)!==$expected->cluster_uuid||($id->version->number??null)!==$expected->version||!is_array($all)||count($all)!==1)throw new RuntimeException('Original search identity changed');
  $s=$all[0];$sh=$s->shards??null;$indices=$s->indices??null;$streams=$s->data_streams??null;
  if(!is_array($indices)||!is_array($streams))throw new RuntimeException('Incomplete snapshot inventory');sort($indices,SORT_STRING);sort($streams,SORT_STRING);
  if(($s->snapshot??null)!=='baseline'||($s->uuid??null)!==$expected->snapshot_uuid||($s->state??null)!=='SUCCESS'||($s->include_global_state??null)!==true||($s->failures??null)!==[]||($s->version??null)!==$expected->version||$indices!==$expected->indices||$streams!==$expected->data_streams||($sh->total??null)!==$expected->shards||($sh->successful??null)!==$expected->shards||($sh->failed??null)!==0)throw new RuntimeException('Original search snapshot changed');
  if((request('GET','/_ilm/status')->operation_mode??null)!=='STOPPED')throw new RuntimeException('Original search writer policy changed');
 }
 // Read the held original dump, validate its full raw pin, and omit exactly its
 // final non-SQL completion timestamp comment. All other bytes stay exact.
 foreach(['/state','/state/framework-db-baseline.sql'] as $p)if(is_link($p))throw new RuntimeException('Linked database baseline');
 $file=fopen('/state/framework-db-baseline.sql','rb');if($file===false)throw new RuntimeException('Database baseline unavailable');$st=fstat($file);
 if(($st['mode']&0170000)!==0100000||$st['nlink']!==1||$st['size']!==(int)$argv[4]||$st['size']<100)throw new RuntimeException('Original regular dump required');
 $projection=new NavigationDumpProjection($port,$argv[6]);$rawhash=hash_init('sha256');$content=hash_init('sha256');$previous=null;$size=0;$first=true;
 while(($line=fgets($file,16777217))!==false){if(hrtime(true)/1e9>=$until||substr($line,-1)!=="\n")throw new RuntimeException('Dump read deadline');if($first){if(substr($line,0,14)!=='-- MySQL dump '&&$line!=="-- MariaDB dump 10.19  Distrib 10.6.12-MariaDB, for Linux (x86_64)\n")throw new RuntimeException('Original mysqldump format required');$first=false;}hash_update($rawhash,$line);if($previous!==null){$projected=$projection->consume($previous);hash_update($content,$projected);$size+=strlen($projected);}$previous=$line;}
 $afterStat=fstat($file);foreach(['dev','ino','mode','nlink','size','mtime','ctime'] as $key)if($afterStat[$key]!==$st[$key])throw new RuntimeException('Original dump changed during read');
 if(!feof($file)||$previous===null||!preg_match('/^-- Dump completed on [0-9]{4}-[0-9]{2}-[0-9]{2} (?:[01][0-9]|2[0-3]| [0-9]):[0-5][0-9]:[0-5][0-9]\n$/D',$previous)||hash_final($rawhash)!==$argv[3])throw new RuntimeException('Changed/incomplete original dump');
 $projection->complete();$dbhash=hash_final($content);fclose($file);$file=null;
 identity();$state=request('GET','/_cluster/state/metadata');$metadata=$state->metadata??null;
 if(!is_object($metadata)||($metadata->cluster_uuid??null)!==$expected->cluster_uuid||!is_object($metadata->indices??null))throw new RuntimeException('Original cluster metadata required');
 $indices=array_keys(get_object_vars($metadata->indices));sort($indices,SORT_STRING);if($indices!==$expected->indices)throw new RuntimeException('Current index inventory differs');
 $metaHash=digest(normalized($metadata));$equivalenceMetaHash=digest(equivalence_metadata($metadata));$documents=[];$seen=[];$total=0;
 foreach($indices as $name){
  if(!preg_match('/^[a-z0-9.][a-z0-9_.-]{0,254}$/D',$name)||in_array($name,['.','..'],true))throw new RuntimeException('Literal index required');
  $reply=request('POST','/'.rawurlencode($name).'/_search?scroll=1m',(object)['size'=>100,'sort'=>['_doc'],'track_total_hits'=>true,'stored_fields'=>['_routing'],'_source'=>false,'query'=>(object)['match_all'=>new stdClass()]]);$count=0;$expectedCount=null;
  do{
   $scroll=$reply->_scroll_id??$scroll;$hits=$reply->hits->hits??null;$t=$reply->hits->total??null;$sh=$reply->_shards??null;
   if(!is_string($scroll)||$scroll===''||strlen($scroll)>65536||($reply->timed_out??null)!==false||($sh->failed??null)!==0||($sh->successful??null)!==($sh->total??null)||!is_array($hits)||!is_object($t)||($t->relation??null)!=='eq'||!is_int($t->value??null))throw new RuntimeException('Incomplete search contents');
   if($expectedCount===null)$expectedCount=$t->value;elseif($expectedCount!==$t->value)throw new RuntimeException('Search count changed');
   foreach($hits as $hit){
    if(!is_object($hit)||($hit->_index??null)!==$name||!is_string($hit->_id??null)||$hit->_id==='')throw new RuntimeException('Complete original document required');
    $routing=$hit->fields->_routing??[];if(!is_array($routing)||count($routing)>1||(count($routing)===1&&!is_string($routing[0])))throw new RuntimeException('Original routing required');
    $key=bytes([$name,$hit->_id,$routing]);if(isset($seen[$key]))throw new RuntimeException('Duplicate original document');$seen[$key]=true;
    // Read original stored source bytes directly: no lossy PHP number decode,
    // empty-object coercion or rewriting of application JSON enters the hash.
    $path='/'.rawurlencode($name).'/_source/'.rawurlencode($hit->_id);if(count($routing))$path.='?routing='.rawurlencode($routing[0]);
    $source=request('GET',$path,null,true);
    $row=(object)['index'=>$name,'id'=>$hit->_id,'source_sha256'=>hash('sha256',$source),'routing'=>$routing];
    $documents[]=digest($row);$count++;$total++;if($total>1000000)throw new RuntimeException('Content inventory too large');
   }
   if(count($hits)===0)break;$reply=request('POST','/_search/scroll',(object)['scroll'=>'1m','scroll_id'=>$scroll]);
  }while(true);
  if($count!==$expectedCount)throw new RuntimeException('Incomplete document count');
  $clear=request('DELETE','/_search/scroll',(object)['scroll_id'=>[$scroll]]);if(($clear->succeeded??null)!==true)throw new RuntimeException('Scroll close unconfirmed');$scroll=null;
 }
 identity();$after=request('GET','/_cluster/state/metadata');
 // Same physical index metadata/version before and after; never normalize a
 // concurrent mutation away. External writer exclusion is still mandatory.
 if(bytes($after->metadata??null)!==bytes($metadata))throw new RuntimeException('Search metadata changed during measurement');
 sort($documents,SORT_STRING);
 $answer=['schema_version'=>'admin-navigation-contents-reply/3','database_raw_sha256'=>$argv[3],'database_content_sha256'=>$dbhash,'database_content_bytes'=>$size,'search_metadata_sha256'=>$metaHash,'search_documents_sha256'=>digest($documents),'search_documents'=>$total,'search_operation_mode'=>'STOPPED','search_equivalence_metadata_sha256'=>$equivalenceMetaHash];
}catch(Throwable $e){$failed=get_class($e).': '.$e->getMessage();}
finally{if(is_resource($file))fclose($file);if($scroll!==null){try{$r=request('DELETE','/_search/scroll',(object)['scroll_id'=>[$scroll]]);if(($r->succeeded??null)!==true)throw new RuntimeException('Scroll close unconfirmed');}catch(Throwable $e){$failed=($failed??'').' | scroll cleanup: '.$e->getMessage();}}}
if($failed!==null){fwrite(STDERR,$failed.PHP_EOL);exit(2);}echo json_encode($answer,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
"""
)
