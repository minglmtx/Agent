"""Exact mysqldump projection for the measured current Admin startup footprint.

Pinned-image schema6364 confirms six columns and automatic updated_at. All
original bytes remain in the recovery dump; only verified CONFIGURE rows have
their declared search port/startup timestamp projected in comparison bytes.
"""

DATABASE_PROJECTION_PHP = r"""
class NavigationDumpProjection {
 private $columns=[];private $inDDL=false;private $ready=false;private $timestamp=false;
 private $seen=[];private $expected=[];private $portPaths=[];private $allScopes=[];
 function __construct($port,$origin) {
  if(!preg_match('/^http:\/\/127\.0\.0\.1:([0-9]{4,5})\/admin$/D',$origin,$m)||(int)$m[1]<1024||(int)$m[1]>65535)throw new RuntimeException('Original declared web origin required');
  $base=substr($origin,0,-5);
  foreach(['web/unsecure/base_url','web/secure/base_url'] as $path){$this->expected["'".$path."'"]="'".$base."'";$this->allScopes["'".$path."'"]=true;}
  foreach(['admin/security/password_is_forced','admin/security/password_lifetime'] as $path){$this->expected["'".$path."'"]="'0'";$this->allScopes["'".$path."'"]=true;}
  foreach(['opensearch','elasticsearch7','elasticsearch6','elasticsearch'] as $engine){
   $host="'catalog/search/".$engine."_server_hostname'";$key="'catalog/search/".$engine."_server_port'";
   $this->expected[$host]="'127.0.0.1'";$this->expected[$key]="'".$port."'";$this->portPaths[$key]=true;
  }
 }
 private function rows($body) {
  if(substr($body,-2)!==";\n")throw new RuntimeException('Incomplete config INSERT');
  $body=substr($body,0,-2);$length=strlen($body);$i=0;$rows=[];
  while($i<$length){
   if($body[$i++]!=='(')throw new RuntimeException('Config row opening required');$row=[];
   while(true){
    if($i>=$length)throw new RuntimeException('Incomplete config value');$start=$i;
    if($body[$i]==="'"){
     $i++;$closed=false;
     while($i<$length){$c=$body[$i++];if($c==='\\'){if($i>=$length)throw new RuntimeException('Incomplete SQL escape');$i++;}elseif($c==="'"){if($i<$length&&$body[$i]==="'"){$i++;continue;}$closed=true;break;}}
     if(!$closed)throw new RuntimeException('Unclosed SQL config literal');
    }else{
     while($i<$length&&$body[$i]!==','&&$body[$i]!==')')$i++;
     $token=substr($body,$start,$i-$start);
     if(!preg_match('/^(NULL|-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?|0x[0-9a-fA-F]+)$/D',$token))throw new RuntimeException('Unsupported config value syntax');
    }
    $row[]=substr($body,$start,$i-$start);if(count($row)>6||$i>=$length)throw new RuntimeException('Incomplete config row');
    $sep=$body[$i++];if($sep===')')break;if($sep!==',')throw new RuntimeException('Config value separator required');
   }
   if(count($row)!==6)throw new RuntimeException('Original six-column config row required');$rows[]=$row;
   if(count($rows)>100000)throw new RuntimeException('Config inventory too large');
   if($i===$length)break;if($body[$i++]!==','||$i===$length)throw new RuntimeException('Config row separator required');
  }
  return $rows;
 }
 private function insert($rows){return 'INSERT INTO `core_config_data` VALUES '.implode(',',array_map(function($r){return '('.implode(',',$r).')';},$rows)).";\n";}
 function consume($line) {
  if($line==="CREATE TABLE `core_config_data` (\n"){
   if($this->inDDL||$this->ready)throw new RuntimeException('Duplicate core config schema');$this->inDDL=true;return $line;
  }
  if($this->inDDL){
   if(preg_match('/^  `([a-z][a-z0-9_]*)` /',$line,$m)){
    $this->columns[]=$m[1];
    if($m[1]==='updated_at')$this->timestamp=(bool)preg_match('/`updated_at` timestamp .*DEFAULT CURRENT_TIMESTAMP(?:\(\))? ON UPDATE CURRENT_TIMESTAMP(?:\(\))?/i',$line);
   }elseif(substr($line,0,9)===') ENGINE='){
    if($this->columns!==['config_id','scope','scope_id','path','value','updated_at']||!$this->timestamp)throw new RuntimeException('Unsupported original config schema');$this->ready=true;$this->inDDL=false;
   }
   return $line;
  }
  $prefix='INSERT INTO `core_config_data` VALUES ';
  if(substr($line,0,strlen($prefix))!==$prefix){
   if(substr($line,0,31)==='INSERT INTO `core_config_data` ')throw new RuntimeException('Unsupported config INSERT format');return $line;
  }
  if(!$this->ready)throw new RuntimeException('Config data before original schema');
  $rows=$this->rows(substr($line,strlen($prefix)));
  if($this->insert($rows)!==$line)throw new RuntimeException('Noncanonical original config INSERT');
  foreach($rows as &$row){
   $key=$row[3];$default=$row[1]==="'default'"&&$row[2]==='0';
   if(isset($this->expected[$key])&&($default||isset($this->allScopes[$key]))){
    if($row[4]!==$this->expected[$key]||!preg_match("/^'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}'$/D",$row[5]))throw new RuntimeException('Measured startup config differs from original declaration');
    if($default&&!isset($this->allScopes[$key])){if(isset($this->seen[$key]))throw new RuntimeException('Duplicate default startup config');$this->seen[$key]=true;}
    if(isset($this->portPaths[$key]))$row[4]="'__DECLARED_LOCAL_SEARCH_PORT__'";
    $row[5]="'__DECLARED_STARTUP_CONFIG_TIME__'";
   }
  }unset($row);
  return $this->insert($rows);
 }
 function complete(){
  if(!$this->ready||$this->inDDL||count($this->seen)!==8)throw new RuntimeException('Complete measured startup configuration required');
 }
}
"""
