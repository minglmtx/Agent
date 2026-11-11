"""Fixed native small-selector/readonly artifact validation before any PG I/O."""

READ_INPUT = r"""
function reddit_keys($value,$expected){
 if(!is_array($value)||array_is_list($value))throw new RuntimeException('Native selector object required');
 $keys=array_keys($value);sort($keys);sort($expected);
 if($keys!==$expected)throw new RuntimeException('Native selector fields differ');
}
function reddit_task($task){
 reddit_keys($task,['schema_version','source_task_id','task_id','split','site','family','contract_version']);
 if($task['schema_version']!=='task-identity/1'||$task['site']!=='reddit'||$task['family']!=='native_image_submission'||$task['contract_version']!==1||$task['split']!=='train')throw new RuntimeException('Selected original native task required');
 foreach(['source_task_id','task_id']as$key)if(!is_string($task[$key])||strlen($task[$key])>256||!preg_match('/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/D',$task[$key]))throw new RuntimeException('Native task identifier invalid');
}
function reddit_same_task($a,$b){
 reddit_task($a);reddit_task($b);
 foreach(array_keys($a)as$key)if($a[$key]!==$b[$key])throw new RuntimeException('Native baseline task differs');
}
function reddit_read_selector(){
 $raw=stream_get_contents(STDIN,8193);
 if(!is_string($raw)||strlen($raw)<1||strlen($raw)>8192)throw new RuntimeException('Native selector exceeds original byte bound');
 $input=json_decode($raw,true,512,JSON_THROW_ON_ERROR);
 reddit_keys($input,['mode','task','username','forum','baseline']);reddit_task($input['task']);
 if(!in_array($input['mode'],['reference','capture'],true)||!is_string($input['username'])||strlen($input['username'])>255||!preg_match('/^[A-Za-z0-9_.-]+$/D',$input['username'])||!is_string($input['forum'])||strlen($input['forum'])<1||strlen($input['forum'])>255||preg_match('/[\x00-\x1f]/',$input['forum']))throw new RuntimeException('Native read mode/account/forum selector invalid');
 if($input['mode']==='reference'){
  if($input['baseline']!==null)throw new RuntimeException('Fresh reference cannot adopt a baseline file');
  return ['selector'=>$input,'baseline_payload'=>null];
 }
 $ref=$input['baseline'];reddit_keys($ref,['schema_version','task','request_sha256','filename','sha256','size_bytes']);
 if($ref['schema_version']!=='reddit-native-baseline-ids-ref/1'||!is_string($ref['request_sha256'])||!preg_match('/^[0-9a-f]{64}$/D',$ref['request_sha256'])||$ref['filename']!==$ref['request_sha256'].'.json'||!is_string($ref['sha256'])||!preg_match('/^[0-9a-f]{64}$/D',$ref['sha256'])||!is_int($ref['size_bytes'])||$ref['size_bytes']<1||$ref['size_bytes']>64*1024*1024)throw new RuntimeException('Original native baseline reference invalid');
 reddit_same_task($ref['task'],$input['task']);
 $path='/native-input/'.$ref['filename'];
 if(realpath($path)!==$path)throw new RuntimeException('Native baseline input uses an alias');
 $before=lstat($path);
 if($before===false||($before['mode']&0170000)!==0100000||$before['nlink']!==1||($before['mode']&0777)!==0400||!function_exists('posix_geteuid')||$before['uid']!==posix_geteuid()||$before['size']!==$ref['size_bytes'])throw new RuntimeException('Owned bounded immutable native baseline input required');
 $h=fopen($path,'rb');if($h===false)throw new RuntimeException('Native baseline input unreadable');
 try{
  $opened=fstat($h);
  foreach(['dev','ino','mode','nlink','uid','gid','size','mtime','ctime']as$key)if($opened[$key]!==$before[$key])throw new RuntimeException('Native baseline input identity changed');
  $data=stream_get_contents($h,$ref['size_bytes']+1);$after=fstat($h);
  foreach(['dev','ino','mode','nlink','uid','gid','size','mtime','ctime']as$key)if($after[$key]!==$before[$key])throw new RuntimeException('Native baseline input changed during read');
 }finally{fclose($h);}
 if(!is_string($data)||strlen($data)!==$ref['size_bytes']||hash('sha256',$data)!==$ref['sha256'])throw new RuntimeException('Native baseline input bytes differ');
 $payload=json_decode($data,true,512,JSON_THROW_ON_ERROR);reddit_keys($payload,['schema_version','task','request_sha256','count','ranges']);
 if($payload['schema_version']!=='reddit-native-baseline-ids/1'||$payload['request_sha256']!==$ref['request_sha256']||!is_int($payload['count'])||$payload['count']<0||!is_array($payload['ranges'])||!array_is_list($payload['ranges'])||count($payload['ranges'])>1000000)throw new RuntimeException('Complete original baseline ids required');
 reddit_same_task($payload['task'],$input['task']);$end=0;$covered=0;
 foreach($payload['ranges']as$range){
  if(!is_array($range)||!array_is_list($range)||count($range)!==2||!is_int($range[0])||!is_int($range[1])||!($end<$range[0]&&$range[0]<=$range[1]))throw new RuntimeException('Native baseline ranges malformed');
  $covered+=$range[1]-$range[0]+1;$end=$range[1];
  if(!is_int($covered)||$covered>$payload['count'])throw new RuntimeException('Native baseline range coverage overflow');
 }
 if($covered!==$payload['count'])throw new RuntimeException('Native baseline id count incomplete');
 return ['selector'=>$input,'baseline_payload'=>$payload];
}
"""
