"""Original PG full-row digest algorithms, read-only and bounded per statement."""

SQL = r"""
function reddit_identifier($name){
 if(!is_string($name)||!preg_match('/^[a-z][a-z0-9_]{0,62}$/D',$name))throw new RuntimeException('Native SQL identifier invalid');
 return '"'.$name.'"';
}
function reddit_integer($value,$positive=false){
 if(!is_int($value)&&!is_string($value))throw new RuntimeException('Native integer type invalid');
 $text=(string)$value;$number=(int)$text;
 if(!preg_match($positive?'/^[1-9][0-9]*$/D':'/^(0|[1-9][0-9]*)$/D',$text)||(string)$number!==$text)throw new RuntimeException('Exact native integer required');
 return $number;
}
function reddit_rows($db,$sql,$parameters=[]){
 $q=$db->prepare("SELECT COALESCE(json_agg(native_rows),'[]'::json)::text FROM (".$sql.') native_rows');
 $q->execute($parameters);$raw=$q->fetchColumn();$q->closeCursor();
 $rows=json_decode($raw,true,512,JSON_THROW_ON_ERROR);
 if(!is_array($rows)||!array_is_list($rows))throw new RuntimeException('Complete native JSON row set required');
 return $rows;
}
function reddit_schema($db){
 $names=reddit_rows($db,"SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name");
 if(count($names)<14||count($names)>512)throw new RuntimeException('Complete native public table scope required');
 $schema=[];
 foreach($names as$row){reddit_identifier($row['table_name']);if(isset($schema[$row['table_name']]))throw new RuntimeException('Duplicate native table');$schema[$row['table_name']]=[];}
 $columns=reddit_rows($db,"SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position");
 foreach($columns as$row){if(!array_key_exists($row['table_name'],$schema))continue;reddit_identifier($row['column_name']);$schema[$row['table_name']][]=$row['column_name'];}
 foreach($schema as$columns)if(count($columns)<1||count($columns)>512||count(array_unique($columns))!==count($columns))throw new RuntimeException('Every native table column required');
 foreach(['forums','comments','submission_votes','comment_votes','wiki_pages','wiki_revisions','forum_tags','forums_tags','hidden_forums','forum_subscriptions','user_blocks','users','submissions','images']as$name)if(!isset($schema[$name]))throw new RuntimeException('Original native public table missing');
 return $schema;
}
function reddit_primary_key($db,$table){
 reddit_identifier($table);
 $rows=reddit_rows($db,"SELECT k.column_name,c.data_type FROM information_schema.table_constraints t JOIN information_schema.key_column_usage k ON k.constraint_name=t.constraint_name AND k.constraint_schema=t.constraint_schema AND k.table_name=t.table_name JOIN information_schema.columns c ON c.table_schema=k.table_schema AND c.table_name=k.table_name AND c.column_name=k.column_name WHERE t.constraint_type='PRIMARY KEY' AND k.table_schema='public' AND k.table_name=? ORDER BY k.ordinal_position",[$table]);
 if(!$rows||count($rows)>16)throw new RuntimeException('Original indexed primary key required');
 $keys=[];$types=[];
 foreach($rows as$row){$keys[]=reddit_identifier($row['column_name']);if(!in_array($row['data_type'],['bigint','integer','smallint','uuid'],true))throw new RuntimeException('Unsupported native primary key type');$types[]=$row['data_type'];}
 if(count(array_unique($keys))!==count($keys))throw new RuntimeException('Duplicate native primary key');
 return [$keys,$types];
}
function reddit_small_digest($db,$table,$excluded_image=null){
 $table_sql=reddit_identifier($table);$where='';$parameters=[];
 if($excluded_image!==null){if($table!=='images'||!is_string($excluded_image)||!preg_match('/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/D',$excluded_image))throw new RuntimeException('Exact native new image UUID required');$where=' WHERE id<>CAST(? AS uuid)';$parameters[]=$excluded_image;}
 $limbs=[];foreach([1,9,17,25]as$i)$limbs[]="COALESCE(sum(('x'||substr(h,".$i.",8))::bit(32)::bigint)::text,'0')";
 $sql="SELECT count(*) AS count,md5(".implode("||':'||",$limbs).") AS digest FROM (SELECT md5(row_to_json(r)::text) AS h FROM ".$table_sql.' r'.$where.' OFFSET 0) full_rows';
 $rows=reddit_rows($db,$sql,$parameters);
 if(count($rows)!==1||!is_int($rows[0]['count'])||$rows[0]['count']<0||!preg_match('/^[0-9a-f]{32}$/D',$rows[0]['digest']))throw new RuntimeException('Exact full native aggregate required');
 return $rows[0];
}
function reddit_heavy_digest($db,$table,$new_post=null){
 if(!in_array($table,['comments','comment_votes','submission_votes','users'],true))throw new RuntimeException('Known native heavy table required');
 [$keys,$types]=reddit_primary_key($db,$table);$table_sql=reddit_identifier($table);$last=null;$count=0;$original_count=0;$ctx=hash_init('md5');$original=hash_init('md5');
 $reference=reddit_integer($db->query('SELECT count(*) FROM '.$table_sql)->fetchColumn());
 $projection=$table==='users'?"(to_jsonb(r)-'last_seen')::text":'row_to_json(r)::text';
 while(true){
  $condition='';$parameters=[];
  if($last!==null){$casts=[];foreach($types as$i=>$type){$casts[]='CAST(? AS '.$type.')';$parameters[]=$last[$i];}$condition=' WHERE ROW('.implode(',',$keys).') > ROW('.implode(',',$casts).')';}
  $extra=$table==='submission_votes'?',submission_id':'';
  $q=$db->prepare('SELECT '.implode(',',$keys).$extra.',md5('.$projection.') AS __lab_row_hash FROM '.$table_sql.' r'.$condition.' ORDER BY '.implode(',',$keys).' LIMIT 2048');$q->execute($parameters);$rows=$q->fetchAll(PDO::FETCH_ASSOC);$q->closeCursor();
  if(!$rows)break;
  foreach($rows as$row){
   $hash=$row['__lab_row_hash'];if(!is_string($hash)||!preg_match('/^[0-9a-f]{32}$/D',$hash))throw new RuntimeException('Native row digest invalid');
   $key=[];foreach($keys as$i=>$name){$column=trim($name,'"');$value=(string)$row[$column];if(!preg_match($types[$i]==='uuid'?'/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/D':'/^-?(0|[1-9][0-9]*)$/D',$value))throw new RuntimeException('Native indexed row key invalid');$key[]=$value;}
   if($last!==null&&$key===$last)throw new RuntimeException('Native indexed scan repeated a key');
   $last=$key;hash_update($ctx,$hash);$count++;
   if($table!=='submission_votes'||$new_post===null||reddit_integer($row['submission_id'],true)!==$new_post){hash_update($original,$hash);$original_count++;}
  }
  if($count>$reference)throw new RuntimeException('Native indexed scan exceeded table count');
 }
 if($count!==$reference||reddit_integer($db->query('SELECT count(*) FROM '.$table_sql)->fetchColumn())!==$reference)throw new RuntimeException('Native indexed coverage incomplete');
 return ['full'=>['count'=>$count,'digest'=>hash_final($ctx)],'original'=>['count'=>$original_count,'digest'=>hash_final($original)]];
}
function reddit_submissions($db,$schema,$baseline){
 if(reddit_primary_key($db,'submissions')[0]!==['"id"'])throw new RuntimeException('Original indexed submission id required');
 $total=reddit_integer($db->query('SELECT count(*) FROM submissions')->fetchColumn());$covered=0;$last=null;$ctx=hash_init('sha256');$old=hash_init('sha256');$old_count=0;$new=[];$ranges=[];$index=0;
 while($covered<$total){
  $q=$db->prepare('SELECT id,md5(row_to_json(s)::text) AS row_md5 FROM submissions s'.($last===null?'':' WHERE id>CAST(? AS bigint)').' ORDER BY id LIMIT 2048');$q->execute($last===null?[]:[$last]);$rows=$q->fetchAll(PDO::FETCH_ASSOC);$q->closeCursor();
  if(count($rows)!==min(2048,$total-$covered))throw new RuntimeException('Full native submission chunk coverage changed');
  foreach($rows as$row){
   $id=reddit_integer($row['id'],true);$hash=$row['row_md5'];if(($last!==null&&$id<=$last)||!is_string($hash)||!preg_match('/^[0-9a-f]{32}$/D',$hash))throw new RuntimeException('Ordered full native submission digest required');
   hash_update($ctx,$hash."\n");$last=$id;
   if($baseline===null){
    $n=count($ranges);if($n>0&&$ranges[$n-1][1]<PHP_INT_MAX&&$ranges[$n-1][1]+1===$id)$ranges[$n-1][1]=$id;else{$ranges[]=[$id,$id];if(count($ranges)>1000000)throw new RuntimeException('Native range count bound');}
    hash_update($old,$hash."\n");$old_count++;
   }else{
    while($index<count($baseline)&&$baseline[$index][1]<$id)$index++;
    if($index<count($baseline)&&$baseline[$index][0]<=$id){hash_update($old,$hash."\n");$old_count++;}
    else{$new[]=$id;if(count($new)>100000)throw new RuntimeException('Unexpected new native post set exceeds evidence bound');}
   }
  }
  $covered+=count($rows);
 }
 if(reddit_integer($db->query('SELECT count(*) FROM submissions')->fetchColumn())!==$total)throw new RuntimeException('Full native submission count changed');
 $full=['count'=>$total,'columns'=>$schema['submissions'],'key'=>['id'],'sha256'=>hash_final($ctx)];
 $original=count($new)===1?['count'=>$old_count,'columns'=>$schema['submissions'],'key'=>['id'],'sha256'=>hash_final($old)]:$full;
 $added=[];
 foreach(array_chunk($new,512)as$ids){
  $sql='SELECT * FROM submissions WHERE id IN('.implode(',',array_fill(0,count($ids),'CAST(? AS bigint)')).') ORDER BY id';
  $added=array_merge($added,reddit_rows($db,$sql,$ids));
 }
 if(count($added)!==count($new))throw new RuntimeException('Complete actual new native post rows required');
 return ['full'=>$full,'original'=>$original,'added'=>$added,'known_id_ranges'=>$ranges];
}
"""
