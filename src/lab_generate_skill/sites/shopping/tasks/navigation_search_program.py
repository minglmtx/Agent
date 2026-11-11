"""Bounded original local ES7 contents, including raw stored source bytes.

No caller URL/index/script; no new snapshot or restore facility. Scroll creation
has effects: failures retain their primary error and separately attempt cleanup.
External cancellation still needs the original instance owner's native close.
V2 excludes the index metadata update counter only across completed measurements;
raw metadata and every within-measurement change remain guarded.
"""

SEARCH_CONTENTS = r"""
$scroll=null;$failed=null;$answer=null;$cleanup=false;$port=0;$until=0;$hard=0;
try {
 if(count($argv)!==3||!ctype_digit($argv[1])||(int)$argv[1]<1024||(int)$argv[1]>65535||!is_numeric($argv[2])||!is_finite((float)$argv[2])||(float)$argv[2]<=6||(float)$argv[2]>86400)throw new RuntimeException('Invalid original search endpoint/budget');
 $port=(int)$argv[1];$hard=hrtime(true)/1e9+(float)$argv[2];$until=$hard-5;
 function canonical($v){if(is_object($v)){$a=get_object_vars($v);ksort($a,SORT_STRING);$r=new stdClass();foreach($a as$k=>$x)$r->$k=canonical($x);return $r;}if(is_array($v))return array_map('canonical',$v);return $v;}
 function bytes($v){return json_encode(canonical($v),JSON_UNESCAPED_SLASHES|JSON_PRESERVE_ZERO_FRACTION|JSON_THROW_ON_ERROR);}
 function digest($v){return hash('sha256',bytes($v));}
 function request($method,$path,$body=null,$source=false){
  global $port,$until,$hard,$cleanup;$remaining=($cleanup?$hard:$until)-hrtime(true)/1e9;if($remaining<=0)throw new RuntimeException('Search contents deadline expired');
  $opts=['method'=>$method,'timeout'=>$remaining,'follow_location'=>0,'ignore_errors'=>true,'header'=>"Content-Type: application/json\r\nConnection: close\r\n"];
  if($body!==null)$opts['content']=bytes($body);
  $s=@fopen('http://127.0.0.1:'.$port.$path,'rb',false,stream_context_create(['http'=>$opts]));$headers=$http_response_header??[];
  if($s===false)throw new RuntimeException('Search contents HTTP failed');
  try{$raw=stream_get_contents($s,16777217);$meta=stream_get_meta_data($s);}finally{fclose($s);}
  if($raw===false||strlen($raw)>16777216||($meta['timed_out']??true)!==false||($meta['eof']??false)!==true||!preg_match('/^HTTP\/[0-9.]+ 200(?: |$)/',$headers[0]??''))throw new RuntimeException('Incomplete search contents HTTP');
  if(!$source){
   $quoted=false;$escaped=false;$outside='';
   for($j=0;$j<strlen($raw);$j++){$c=$raw[$j];if($quoted){if($escaped)$escaped=false;elseif($c==='\\')$escaped=true;elseif($c==='"')$quoted=false;}else{if($c==='"'){$quoted=true;$outside.=' ';}else$outside.=$c;}}
   preg_match_all('/-?[0-9][0-9.eE+\-]*/',$outside,$numbers);foreach($numbers[0]as$n)if(!preg_match('/^-?(0|[1-9][0-9]{0,14})$/D',$n))throw new RuntimeException('Unsupported exact search metadata number');
  }
  $v=json_decode($raw,false,128,JSON_THROW_ON_ERROR|JSON_BIGINT_AS_STRING);if(!is_object($v))throw new RuntimeException('Search contents JSON object required');return $source?$raw:$v;
 }
 function identity(){
  $v=request('GET','/');$uuid=$v->cluster_uuid??null;$version=$v->version->number??null;
  if(!is_string($uuid)||!preg_match('/^[A-Za-z0-9_-]{1,128}$/D',$uuid)||!is_string($version)||!preg_match('/^7\.[0-9]+\.[0-9]+$/D',$version))throw new RuntimeException('Unsupported original search identity/version');return [$uuid,$version];
 }
 function metadata($id){
  $m=request('GET','/_cluster/state/metadata')->metadata??null;
  if(!is_object($m)||($m->cluster_uuid??null)!==$id[0]||!is_object($m->indices??null)||count(get_object_vars($m->indices))>256)throw new RuntimeException('Complete original search metadata required');
  foreach($m->indices as$name=>$row){if(!preg_match('/^[a-z0-9.][a-z0-9_.-]{0,254}$/D',$name)||in_array($name,['.','..'],true)||($row->state??null)!=='open'||!is_int($row->version??null)||$row->version<1||!is_object($row->settings->index??null)||!is_object($row->mappings??null)||!is_array($row->aliases??null))throw new RuntimeException('Unsupported original index metadata');}
  return $m;
 }
 function watermark($names,$m){
  $v=request('GET','/_stats?expand_wildcards=all&level=shards&filter_path=_shards,indices.*.shards.*.routing,indices.*.shards.*.seq_no');$sh=$v->_shards??null;$rows=$v->indices??null;
  if(!is_object($sh)||!is_int($sh->total??null)||$sh->total<0||!is_int($sh->successful??null)||$sh->successful<0||$sh->successful>$sh->total||($sh->failed??null)!==0||!is_object($rows))throw new RuntimeException('Incomplete original shard watermark');
  $got=array_keys(get_object_vars($rows));sort($got,SORT_STRING);if($got!==$names)throw new RuntimeException('Changed original search watermark inventory');
  foreach($rows as$name=>$row){$expected=$m->indices->$name->settings->index->number_of_shards??null;if(!is_string($expected)||!ctype_digit($expected)||(int)$expected<1||!is_object($row->shards??null)||count(get_object_vars($row->shards))!==(int)$expected)throw new RuntimeException('Missing original shard watermark');foreach($row->shards as$copies){if(!is_array($copies)||count($copies)===0)throw new RuntimeException('Missing original shard copies');$primaries=0;foreach($copies as$copy){if(($copy->routing->primary??null)===true)$primaries++;if(($copy->routing->state??null)!=='STARTED'||!is_bool($copy->routing->primary??null)||!is_object($copy->seq_no??null))throw new RuntimeException('Unstable original shard');foreach(['max_seq_no','local_checkpoint','global_checkpoint']as$k)if(!is_int($copy->seq_no->$k??null)||$copy->seq_no->$k< -1)throw new RuntimeException('Incomplete original sequence watermark');}if($primaries!==1)throw new RuntimeException('Original primary shard missing or duplicated');}}
  return $v;
 }
 function aliases($names,$m){
  $v=request('GET','/_all?expand_wildcards=all');$got=array_keys(get_object_vars($v));sort($got,SORT_STRING);if($got!==$names)throw new RuntimeException('Incomplete original alias inventory');$aliases=new stdClass();
  foreach($v as$name=>$row){if(!is_object($row->aliases??null))throw new RuntimeException('Incomplete original alias definitions');$a=array_keys(get_object_vars($row->aliases));sort($a,SORT_STRING);$expected=$m->indices->$name->aliases;sort($expected,SORT_STRING);if($a!==$expected)throw new RuntimeException('Changed original alias names');$aliases->$name=(object)['aliases'=>$row->aliases];}
  return $aliases;
 }
 function projected($m){$m=unserialize(serialize($m));unset($m->cluster_uuid,$m->cluster_uuid_committed,$m->cluster_coordination);foreach($m->indices as$row)unset($row->version,$row->settings->index->uuid,$row->settings->index->creation_date,$row->primary_terms,$row->in_sync_allocations);return $m;}
 $id=identity();$before=metadata($id);$names=array_keys(get_object_vars($before->indices));sort($names,SORT_STRING);$water=watermark($names,$before);$aliases=aliases($names,$before);$indices=new stdClass();$total=0;
 foreach($names as$name){
  $reply=request('POST','/'.rawurlencode($name).'/_search?scroll=1m',(object)['size'=>100,'sort'=>['_doc'],'track_total_hits'=>true,'stored_fields'=>['_routing'],'_source'=>false,'query'=>(object)['match_all'=>new stdClass()]]);$count=0;$expected=null;$digests=[];$seen=[];
  do{
   $next=$reply->_scroll_id??null;if(is_string($next)&&$next!==''&&strlen($next)<=65536)$scroll=$next;
   $hits=$reply->hits->hits??null;$t=$reply->hits->total??null;$sh=$reply->_shards??null;
   if($scroll===null||!is_string($next)||$next!==$scroll||($reply->timed_out??null)!==false||!is_int($sh->total??null)||$sh->total<0||($sh->failed??null)!==0||($sh->successful??null)!==$sh->total||!is_array($hits)||!is_object($t)||($t->relation??null)!=='eq'||!is_int($t->value??null)||$t->value<0||$t->value>1000000)throw new RuntimeException('Incomplete original scroll');
   if($expected===null)$expected=$t->value;elseif($expected!==$t->value)throw new RuntimeException('Original scroll count changed');
   foreach($hits as$hit){
    if(!is_object($hit)||($hit->_index??null)!==$name||!is_string($hit->_id??null)||$hit->_id===''||strlen($hit->_id)>65536)throw new RuntimeException('Incomplete original document identity');
    $routing=$hit->fields->_routing??[];if(!is_array($routing)||count($routing)>1||(count($routing)===1&&!is_string($routing[0])))throw new RuntimeException('Unsupported original document routing');
    $key=bytes([$hit->_id,$routing]);if(isset($seen[$key]))throw new RuntimeException('Duplicate original document');$seen[$key]=true;
    $path='/'.rawurlencode($name).'/_source/'.rawurlencode($hit->_id).'?realtime=false';if(count($routing))$path.='&routing='.rawurlencode($routing[0]);
    $source=request('GET',$path,null,true);$digests[]=digest([$hit->_id,$routing,hash('sha256',$source)]);$count++;$total++;if($total>1000000||$count>$expected)throw new RuntimeException('Complete original contents exceed declared count/bound');
   }
   if(count($hits)===0)break;$reply=request('POST','/_search/scroll',(object)['scroll'=>'1m','scroll_id'=>$scroll]);
  }while(true);
  if($count!==$expected)throw new RuntimeException('Incomplete original document count');
  $r=request('DELETE','/_search/scroll',(object)['scroll_id'=>[$scroll]]);if(($r->succeeded??null)!==true)throw new RuntimeException('Original scroll cleanup unconfirmed');$scroll=null;
  sort($digests,SORT_STRING);$indices->$name=['documents'=>$count,'documents_sha256'=>digest($digests)];
 }
 if(identity()!==$id||bytes(metadata($id))!==bytes($before)||bytes(watermark($names,$before))!==bytes($water)||bytes(aliases($names,$before))!==bytes($aliases))throw new RuntimeException('Original search changed during contents measurement');
 $answer=['schema_version'=>'shopping-navigation-search-contents/1','search_port'=>$port,'cluster_uuid'=>$id[0],'version'=>$id[1],'normalization'=>'original-shopping-search-physical-identity-v2','raw_metadata_sha256'=>digest($before),'metadata_sha256'=>digest(projected($before)),'aliases_sha256'=>digest($aliases),'mutation_watermark_sha256'=>digest($water),'indices'=>$indices,'documents'=>$total,'complete_scrolls'=>true,'cleanup_confirmed'=>true];
}catch(Throwable $e){$failed=get_class($e).': '.$e->getMessage();}
finally{if($scroll!==null){$cleanup=true;try{$r=request('DELETE','/_search/scroll',(object)['scroll_id'=>[$scroll]]);if(($r->succeeded??null)!==true)throw new RuntimeException('Original scroll cleanup unconfirmed');}catch(Throwable $e){$failed=($failed??'').' | scroll cleanup: '.$e->getMessage();}}}
if($failed!==null){fwrite(STDERR,$failed.PHP_EOL);exit(2);}echo json_encode($answer,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
"""
