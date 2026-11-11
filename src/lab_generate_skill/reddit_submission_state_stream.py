"""Exact legacy submission_state through one fresh indexed native read.

Preserve MD5(concatenated MD5 of the original ordered CONTENT_COLUMNS JSON),
all native known-ID ranges, low-ID additions and original public forum rows.
No cached snapshot, reduced scan, larger query timeout or evaluator relaxation.
"""
import json,re,subprocess
from .site_database import DatabaseReadError
VERSION='reddit-legacy-submission-state-indexed-stream-v1'
CHUNK=2048
COLUMNS=('id','forum_id','user_id','title','url','body','image_id','media_type','visibility')
PHP=r'''$p=new PDO('pgsql:host=/state/run;port='.$argv[1].';dbname=postmill','postmill',null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_EMULATE_PREPARES=>false]);
try{
 $input=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
 if(!is_array($input)||count($input)!==2||!is_string($input['username'])||!array_key_exists('ranges',$input))throw new RuntimeException('Exact state parameters required');
 $ranges=$input['ranges'];$initial=$ranges===null;
 if(!$initial&&!is_array($ranges))throw new RuntimeException('Exact baseline ranges required');
 $end=0;if(!$initial)foreach($ranges as $r){if(!is_array($r)||count($r)!==2||!is_int($r[0])||!is_int($r[1])||!($end<$r[0]&&$r[0]<=$r[1]))throw new RuntimeException('Exact disjoint positive integer ranges required');$end=$r[1];}
 $p->exec('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');
 $p->exec("SET LOCAL statement_timeout='20s'");
 $q=$p->prepare('SELECT id FROM users WHERE username=?');$q->execute([$input['username']]);$users=$q->fetchAll(PDO::FETCH_ASSOC);$q->closeCursor();
 if(count($users)!==1)throw new RuntimeException('Exact task account required');
 $total=(int)$p->query('SELECT count(*) FROM submissions')->fetchColumn();
 $last=0;$covered=0;$chunk=0;$protected=0;$cursor=0;$outRanges=$initial?[]:$ranges;$added=[];$digest=hash_init('md5');$started=microtime(true);
 while($covered<$total){
  $q=$p->prepare('SELECT id,row_to_json(r) AS row_json,md5(row_to_json(r)::text) AS row_md5 FROM (SELECT id,forum_id,user_id,title,url,body,image_id,media_type,visibility FROM submissions WHERE id>CAST(? AS bigint) ORDER BY id LIMIT 2048) r ORDER BY id');
  $q->execute([$last]);$rows=$q->fetchAll(PDO::FETCH_ASSOC);$q->closeCursor();
  if(count($rows)!==min(2048,$total-$covered))throw new RuntimeException('Complete indexed native chunk required');
  foreach($rows as $row){
   $text=(string)$row['id'];$id=(int)$text;$hash=$row['row_md5'];
   if(!preg_match('/^[1-9][0-9]*$/D',$text)||(string)$id!==$text||$id<=$last||!preg_match('/^[0-9a-f]{32}$/D',$hash))throw new RuntimeException('Exact native id-order row hashes required');
   if($initial){$n=count($outRanges);if($n&&$outRanges[$n-1][1]+1===$id)$outRanges[$n-1][1]=$id;else $outRanges[]=[$id,$id];$old=true;}
   else{while($cursor<count($ranges)&&$ranges[$cursor][1]<$id)$cursor++;$old=$cursor<count($ranges)&&$ranges[$cursor][0]<=$id&&$id<=$ranges[$cursor][1];}
   if($old){hash_update($digest,$hash);$protected++;}else $added[]=json_decode($row['row_json'],true,512,JSON_THROW_ON_ERROR);
   $last=$id;
  }
  $covered+=count($rows);$chunk++;
  echo 'LAB_STATE_CHUNK ',json_encode(['chunk'=>$chunk,'rows'=>count($rows),'covered'=>$covered,'total'=>$total,'seconds'=>microtime(true)-$started]),"\n";flush();
 }
 if((int)$p->query('SELECT count(*) FROM submissions')->fetchColumn()!==$total)throw new RuntimeException('Native snapshot count changed');
 $forumRows=$p->query('SELECT row_to_json(r) AS row_json FROM (SELECT id,name FROM forums ORDER BY id) r')->fetchAll(PDO::FETCH_ASSOC);$forums=[];foreach($forumRows as $r)$forums[]=json_decode($r['row_json'],true,512,JSON_THROW_ON_ERROR);
 $value=['user_id'=>(int)$users[0]['id'],'known_id_ranges'=>$outRanges,'protected_content'=>['count'=>$protected,'digest'=>hash_final($digest)],'forums'=>$forums,'added'=>$added];
 $p->exec('ROLLBACK');echo 'LAB_STATE_RESULT ',json_encode($value,JSON_THROW_ON_ERROR),"\n";flush();
}catch(Throwable $e){if($p->inTransaction())$p->rollBack();fwrite(STDERR,'LAB_STATE_ERROR {"sqlstate":null}' . "\n");exit(42);}'''

def validate_state(state,baseline=None):
 if not isinstance(state,dict)or set(state)!={'user_id','known_id_ranges','protected_content','forums','added'}:raise ValueError('Exact legacy state fields required')
 if type(state['user_id'])is not int or state['user_id']<=0:raise ValueError('Exact native user id required')
 end=0
 for value in state['known_id_ranges']:
  if not isinstance(value,list)or len(value)!=2 or any(type(v)is not int for v in value)or not end<value[0]<=value[1]:raise ValueError('Complete original native ranges required')
  end=value[1]
 protected=state['protected_content']
 if set(protected)!={'count','digest'}or type(protected['count'])is not int or protected['count']<0 or not re.fullmatch('[0-9a-f]{32}',str(protected['digest'])):raise ValueError('Exact old content digest required')
 if not isinstance(state['forums'],list)or not isinstance(state['added'],list):raise ValueError('All native forum/addition rows required')
 for row in state['added']:
  if set(row)!=set(COLUMNS)or type(row['id'])is not int or row['id']<=0:raise ValueError('Complete native addition row required')
  if any(a<=row['id']<=b for a,b in state['known_id_ranges']):raise ValueError('Protected baseline row cannot be a new addition')
 if baseline is not None and (state['user_id']!=baseline['user_id']or state['known_id_ranges']!=baseline['known_id_ranges']):raise ValueError('Original native state binding changed')
 return state

def parse_output(text,baseline=None):
 result=None;covered=0;chunks=0;total=None;progress=[]
 for line in text.splitlines():
  if result is not None:raise ValueError('Unexpected data after native final state')
  if line.startswith('LAB_STATE_CHUNK '):
   row=json.loads(line[len('LAB_STATE_CHUNK '):]);n=row.get('total')
   if set(row)!={'chunk','rows','covered','total','seconds'}or type(n)is not int or n<0 or type(row['chunk'])is not int or row['chunk']!=chunks+1 or type(row['rows'])is not int or row['rows']!=min(CHUNK,n-covered)or row['rows']<=0 or row['covered']!=covered+row['rows']or (total is not None and total!=n):raise ValueError('Native complete chunk coverage required')
   covered=row['covered'];chunks+=1;total=n;progress.append(row)
  elif line.startswith('LAB_STATE_RESULT '):result=validate_state(json.loads(line[len('LAB_STATE_RESULT '):]),baseline)
  elif line.strip():raise ValueError('Unexpected native state output')
 if result is None:raise ValueError('Native final state unavailable')
 if covered!=result['protected_content']['count']+len(result['added']):raise ValueError('Protected and added rows must cover the complete native table')
 return result,progress

def submission_state(site,username,baseline=None):
 if getattr(site,'domain',None)!='reddit' or not isinstance(username,str)or not username:raise ValueError('Native Reddit account required')
 if baseline is not None:validate_state(baseline)
 params=json.dumps({'username':username,'ranges':None if baseline is None else baseline['known_id_ranges']})
 try:
  completed=site.command(['php','-r',PHP,str(site.db_port)],input=params,capture_output=True,text=True,timeout=40)
 except subprocess.CalledProcessError:
  raise DatabaseReadError('LAB_DB_ERROR {"sqlstate":null,"driver_code":null}')from None
 result,progress=parse_output(completed.stdout,baseline)
 logs=getattr(site,'logs',None)
 if logs is not None:
  with (logs/'legacy-submission-state-stream-progress.jsonl').open('a')as output:
   for row in progress:output.write(json.dumps(row)+'\n')
 return result
