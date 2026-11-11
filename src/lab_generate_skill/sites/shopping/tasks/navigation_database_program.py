"""Fixed full SQL measurement; no caller SQL, scripts, credentials or row output."""

from .navigation_database_projection import SCHEMA_PROJECTION

DATABASE_CONTENTS = SCHEMA_PROJECTION + r"""
// Original Shopping complete database contents, not a replacement for Reset.
if(count($argv)!==4||!preg_match('/^http:\/\/127\.0\.0\.1:[0-9]+\/$/',$argv[1])||!ctype_digit($argv[2])||!ctype_digit($argv[3])||(string)(int)$argv[3]!==$argv[3])throw new RuntimeException('Exact original endpoints and monotonic deadline required');
$endpoint=$argv[1];$searchPort=(int)$argv[2];if($searchPort<1024||$searchPort>65535)throw new RuntimeException('Invalid original search port');
$deadline=(int)$argv[3];$initialRemaining=$deadline-hrtime(true);if($initialRemaining<=0||$initialRemaining>86400000000000)throw new RuntimeException('Invalid or expired original SQL measurement deadline');
$env=include '/var/www/magento2/app/etc/env.php';$d=$env['db']['connection']['default'];$host=explode(':',$d['host']);
$p=new PDO('mysql:host='.$host[0].';port='.$host[1].';dbname='.$d['dbname'],$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_STRINGIFY_FETCHES=>true,PDO::MYSQL_ATTR_USE_BUFFERED_QUERY=>false]);
$statementSetting=null;
function navigation_query($sql){
 global$p,$deadline,$statementSetting;
 $milliseconds=intdiv($deadline-hrtime(true),1000000);if($milliseconds<1)throw new RuntimeException('Original SQL measurement deadline exhausted');
 if($statementSetting!==null){$limit=$statementSetting==='max_statement_time'?sprintf('%.3F',$milliseconds/1000):(string)$milliseconds;$p->exec('SET SESSION '.$statementSetting.'='.$limit);}
 elseif($sql!=='SELECT VERSION() AS version')throw new RuntimeException('Original SQL version must be read first');
 if(hrtime(true)>=$deadline)throw new RuntimeException('Original SQL measurement deadline exhausted');
 return$p->query($sql);
}
function fetchAllRows($sql){$q=navigation_query($sql);$v=$q->fetchAll(PDO::FETCH_ASSOC);$q->closeCursor();return$v;}
function identifier($v){if(!preg_match('/^[A-Za-z0-9_]+$/',$v))throw new RuntimeException('Unsupported original SQL identifier');return'`'.$v.'`';}
$version=fetchAllRows('SELECT VERSION() AS version')[0]['version'];$statementSetting=stripos($version,'MariaDB')!==false?'max_statement_time':'max_execution_time';
$p->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');$p->exec('START TRANSACTION READ ONLY');
try{
 $names=[];$kinds=[];foreach(fetchAllRows('SHOW FULL TABLES')as$row){$v=array_values($row);if(count($v)!==2||!in_array($v[1],['BASE TABLE','VIEW'],true))throw new RuntimeException('Unknown unmeasured database object');$names[]=$v[0];$kinds[$v[0]]=$v[1];}
 sort($names,SORT_STRING);$nameHash=hash('sha256',json_encode($names,JSON_THROW_ON_ERROR));
 if(count($names)!==370||$nameHash!=='f9d2f3065ebd472d73446bdbed661f302948ed264be8d2f32d7715c8f8a7c339')throw new RuntimeException('Original complete370 table inventory changed');
 $paths=['web/unsecure/base_url'=>$endpoint,'web/secure/base_url'=>$endpoint];foreach(['opensearch','elasticsearch7','elasticsearch6','elasticsearch']as$engine){$paths['catalog/search/'.$engine.'_server_hostname']='127.0.0.1';$paths['catalog/search/'.$engine.'_server_port']=(string)$searchPort;}
 $observed=[];$out=[];$totalRows=0;
 foreach($names as$name){
  $quoted=identifier($name);$metadata=fetchAllRows('SHOW FULL COLUMNS FROM '.$quoted);$columns=array_column($metadata,'Field');if(!$columns||count($columns)>1024||count(array_unique($columns))!==count($columns))throw new RuntimeException('Incomplete SQL columns');
  $create=fetchAllRows(($kinds[$name]==='VIEW'?'SHOW CREATE VIEW ':'SHOW CREATE TABLE ').$quoted);$rawSchemaHash=hash('sha256',json_encode([$kinds[$name],$metadata,$create],JSON_THROW_ON_ERROR));$projectedCreate=$create;
  if(in_array($name,['core_config_data','customer_visitor','session'],true)&&$kinds[$name]==='BASE TABLE'){
   if(count($create)!==1||($create[0]['Table']??null)!==$name||!isset($create[0]['Create Table']))throw new RuntimeException('Original startup/runtime definition required');
   $projectedCreate[0]['Create Table']=navigation_project_create($create[0]['Create Table']);
  }
  $schemaHash=hash('sha256',json_encode([$kinds[$name],$metadata,$projectedCreate],JSON_THROW_ON_ERROR));
  $order=implode(',',array_map(fn($column)=>'BINARY '.identifier($column),$columns));
  $q=navigation_query('SELECT * FROM '.$quoted.' ORDER BY '.$order);$rawHash=hash_init('sha256');$contentHash=hash_init('sha256');$rows=0;
  while($row=$q->fetch(PDO::FETCH_ASSOC)){
   if(array_keys($row)!==$columns)throw new RuntimeException('SQL row omitted or reordered columns');
   $logical=$row;
   if($name==='core_config_data'&&isset($paths[$row['path']??''])){
    $path=$row['path'];if($row['value']!==$paths[$path])throw new RuntimeException('Original startup configuration value differs from physical service');
    $observed[$path]=true;$logical['value']=str_starts_with($path,'web/')?'<ORIGINAL_WEB_ENDPOINT>':(str_ends_with($path,'_server_port')?'<ORIGINAL_SEARCH_PORT>':'127.0.0.1');
   }
   // Every cell is encoded, including arbitrary binary bytes and explicit NULL.
   $encode=fn($v)=>json_encode(array_map(fn($cell)=>$cell===null?null:base64_encode((string)$cell),array_values($v)),JSON_THROW_ON_ERROR)."\n";
   $raw=$encode($row);$content=$encode($logical);if(strlen($raw)>8*1024*1024||++$totalRows>20000000)throw new RuntimeException('Complete SQL contents exceed explicit measurement bound');
   hash_update($rawHash,$raw);hash_update($contentHash,$content);$rows++;
  }
  $q->closeCursor();$count=(int)array_values(fetchAllRows('SELECT COUNT(*) AS n FROM '.$quoted)[0])[0];if($rows!==$count)throw new RuntimeException('Full SQL row count changed');
  $out[$name]=['kind'=>$kinds[$name],'columns'=>$columns,'rows'=>$rows,'schema_sha256'=>$schemaHash,'raw_schema_sha256'=>$rawSchemaHash,'raw_rows_sha256'=>hash_final($rawHash),'content_rows_sha256'=>hash_final($contentHash)];
  fwrite(STDERR,'LAB_CATEGORY_CONTENTS '.json_encode(['table'=>$name,'rows'=>$rows],JSON_THROW_ON_ERROR)."\n");
 }
 $configured=array_keys($observed);sort($configured,SORT_STRING);$required=array_keys($paths);sort($required,SORT_STRING);if($configured!==$required)throw new RuntimeException('Missing original startup configuration rows');
 $p->exec('ROLLBACK');
 echo json_encode(['schema_version'=>'shopping-navigation-database-contents/2','table_names_sha256'=>$nameHash,'normalization'=>'original-shopping-startup-endpoints-and-counters-v2','runtime_row_tables'=>['customer_visitor','session'],'web_endpoint'=>$endpoint,'search_port'=>$searchPort,'configured_paths'=>$configured,'tables'=>$out,'read_only_consistent_transaction'=>true],JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES);
}catch(Throwable$error){try{fwrite(STDERR,'LAB_CATEGORY_DATABASE_FAILURE '.json_encode(['type'=>get_class($error),'code'=>$error->getCode(),'sqlstate'=>$error instanceof PDOException?($error->errorInfo[0]??null):null,'driver_code'=>$error instanceof PDOException?($error->errorInfo[1]??null):null],JSON_THROW_ON_ERROR)."\n");}catch(Throwable$diagnostic){}try{$p->exec('ROLLBACK');}catch(Throwable$cleanup){fwrite(STDERR,"LAB_CATEGORY_TRANSACTION_CLOSE_FAILURE\n".(string)$cleanup."\n");}throw$error;}
"""
