"""Current native account/forum/full13/auxiliary/image/vote read, no UI effects."""

from .native_input_program import READ_INPUT
from .native_sql_program import SQL

CAPTURE = READ_INPUT + SQL + r"""
$phase='selector';$db=null;
try{
 $selected=reddit_read_selector();$input=$selected['selector'];$baseline=$selected['baseline_payload'];
 $port=filter_var($argv[1]??null,FILTER_VALIDATE_INT,['options'=>['min_range'=>1024,'max_range'=>65535]]);
 if($port===false)throw new RuntimeException('Original native PG port required');
 $phase='connect';$db=new PDO('pgsql:host=/runtime;port='.$port.';dbname=postmill','postmill',null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_EMULATE_PREPARES=>false]);
 $db->exec('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');$db->exec("SET LOCAL statement_timeout='20s'");
 $phase='schema';$schema=reddit_schema($db);
 if($schema['images']!==['id','file_name','sha256','width','height']){
  $columns=$schema['images'];sort($columns);$expected=['id','file_name','sha256','width','height'];sort($expected);
  if($columns!==$expected)throw new RuntimeException('Every original native images column required');
 }
 $phase='account';$accounts=reddit_rows($db,'SELECT id,username FROM users WHERE username=?',[$input['username']]);
 $forums=reddit_rows($db,'SELECT id,name FROM forums ORDER BY id');$target=array_values(array_filter($forums,static fn($f)=>$f['name']===$input['forum']));
 if(count($accounts)!==1||count($target)!==1||!is_int($accounts[0]['id'])||$accounts[0]['id']<=0)throw new RuntimeException('Existing native original account/requested forum required');
 $forum_ids=[];foreach($forums as$f){if(!is_int($f['id'])||$f['id']<=0)throw new RuntimeException('Original native forum identity invalid');$forum_ids[]=$f['id'];}
 if($input['mode']==='reference'){
  $phase='initial-images';$photos=['f81de71a1d4962a541210f1bdd2059c0aeb016d639084102d67e8e62c06c025b','c7c9a1b3c6f035d93c274ae68d5b7d8c49cfaafa7d4d640daf8383d0f52479c8'];
  if(reddit_rows($db,"SELECT id FROM images WHERE encode(sha256,'hex') IN (?,?)",$photos))throw new RuntimeException('Declared fixed photograph already exists in original native image rows');
 }
 $phase='submissions';$posts=reddit_submissions($db,$schema,$baseline['ranges']??null);$new_post=count($posts['added'])===1?$posts['added'][0]['id']:null;
 if($new_post!==null&&(!is_int($new_post)||$new_post<=0))throw new RuntimeException('Actual positive new post id required');
 $image=null;
 if($new_post!==null&&$posts['added'][0]['image_id']!==null){
  $phase='image';$uuid=$posts['added'][0]['image_id'];
  if(!is_string($uuid)||!preg_match('/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/D',$uuid))throw new RuntimeException('Actual native image association UUID required');
  $images=reddit_rows($db,"SELECT id,file_name,encode(sha256,'hex') AS sha256,width,height FROM images WHERE id=CAST(? AS uuid)",[$uuid]);
  if(count($images)!==1)throw new RuntimeException('Actual attached native image row missing');$image=$images[0];
 }
 $phase='protected12';$tables=[];$vote_original=null;
 $protected=['forums','comments','submission_votes','comment_votes','wiki_pages','wiki_revisions','forum_tags','forums_tags','hidden_forums','forum_subscriptions','user_blocks','users'];
 $heavy=['comments','comment_votes','submission_votes','users'];
 foreach($protected as$table){
  $phase='protected-'.$table;
  if(in_array($table,$heavy,true)){
   $result=reddit_heavy_digest($db,$table,$new_post);$tables[$table]=$result['full'];
   if($table==='submission_votes')$vote_original=$result['original'];
  }else{$tables[$table]=reddit_small_digest($db,$table);}
 }
 if($vote_original===null)throw new RuntimeException('Original complete vote scope missing');
 $phase='new-votes';$new_votes=$new_post===null?[]:reddit_rows($db,'SELECT * FROM submission_votes WHERE submission_id=CAST(? AS bigint) ORDER BY id',[$new_post]);
 $phase='auxiliary';$aux=[];
 foreach($schema as$table=>$columns){
  if(in_array($table,array_merge($protected,['submissions']),true))continue;
  $phase='auxiliary-'.$table;$digest=reddit_small_digest($db,$table,$table==='images'&&$image!==null?$image['id']:null);$aux[$table]=array_merge(['columns'=>$columns],$digest);
 }
 $db->exec('ROLLBACK');$db=null;
 $capture=['complete13'=>['version'=>'reddit45-readonly-complete13-v1','twelve_task_tables'=>$tables,'submissions'=>$posts['full'],'users_only_ignored_column'=>'last_seen'],'all_original_submissions'=>$posts['original'],'auxiliary'=>['all_public_tables'=>array_keys($schema),'all_public_schemas'=>$schema,'auxiliary'=>$aux,'excluded_only_new_image_id'=>$image['id']??null],'added_posts'=>$posts['added'],'attached_image'=>$image,'full_original_vote_scope'=>['original'=>$vote_original,'new_post_votes'=>$new_votes,'excluded_only_new_post_id'=>$new_post]];
 $reference=$input['mode']==='reference'?['version'=>'reddit-native-real-photo-candidate-v1','account'=>$accounts[0],'target_forum'=>$target[0],'existing_forum_ids'=>$forum_ids,'known_id_ranges'=>$posts['known_id_ranges']]:null;
 $value=['schema_version'=>'reddit-native-database-capture/1','task'=>$input['task'],'mode'=>$input['mode'],'reference'=>$reference,'capture'=>$capture];
 $output=json_encode($value,JSON_THROW_ON_ERROR);if(strlen($output)>64*1024*1024)throw new RuntimeException('Complete native capture byte bound');echo $output;
}catch(Throwable$e){
 $cleanup=null;try{if($db!==null&&$db->inTransaction())$db->rollBack();}catch(Throwable$close){$cleanup=['class'=>get_class($close),'message'=>$close->getMessage()];}
 $code=$e instanceof PDOException?($e->errorInfo[0]??null):null;
 fwrite(STDERR,'REDDIT_NATIVE_READ_ERROR '.json_encode(['phase'=>$phase,'sqlstate'=>$code,'class'=>get_class($e),'message'=>$e->getMessage(),'cleanup_error'=>$cleanup],JSON_THROW_ON_ERROR)."\n");exit(42);
}
"""
