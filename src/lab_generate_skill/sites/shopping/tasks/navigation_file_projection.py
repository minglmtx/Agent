"""Data-only parser for original CONFIGURE var_export and fixed search controls.

Only endpoint scalar spans are replaced; all other original bytes stay exact.
Snapshot env.php is tokenized, never included/evaluated/executed.
"""

FILE_PROJECTION = r"""
class ShoppingNavigationConfig {
 private $tokens=[];private $i=0;private $values=[];private $arrays=[];
 function __construct($raw){
  if(strlen($raw)>1048576)throw new RuntimeException('Original configuration exceeds bound');
  $offset=0;foreach(token_get_all($raw)as$t){$kind=is_array($t)?$t[0]:$t;$text=is_array($t)?$t[1]:$t;$this->tokens[]=[$kind,$text,$offset];$offset+=strlen($text);}
  $this->take(T_OPEN_TAG);$this->take(T_RETURN);if($this->value([],0)[0]!=='array')throw new RuntimeException('Original configuration root must be array');$this->take(';');if($this->peek()!==null)throw new RuntimeException('Unexpected original configuration code');
 }
 private function peek(){while(isset($this->tokens[$this->i])&&in_array($this->tokens[$this->i][0],[T_WHITESPACE,T_COMMENT,T_DOC_COMMENT],true))$this->i++;return $this->tokens[$this->i]??null;}
 private function take($kind){$t=$this->peek();if($t===null||$t[0]!==$kind)throw new RuntimeException('Unsupported original configuration data syntax');$this->i++;return $t;}
 private function text($t){
  $s=$t[1];if(strlen($s)<2||$s[0]!=="'"||substr($s,-1)!=="'")throw new RuntimeException('Original exported single quoted string required');$out='';
  for($j=1;$j<strlen($s)-1;$j++){if($s[$j]==='\\'&&$j+1<strlen($s)-1&&in_array($s[$j+1],["'",'\\'],true))$j++;$out.=$s[$j];}return $out;
 }
 private function scalar(){
  $t=$this->peek();if($t===null)throw new RuntimeException('Missing original configuration value');$start=$t[2];$sign='';if($t[0]==='-'){$sign='-';$this->i++;$t=$this->peek();}
  if($t===null)throw new RuntimeException('Missing original configuration number');
  if($t[0]===T_CONSTANT_ENCAPSED_STRING&&$sign===''){$v=['string',$this->text($t)];}
  elseif($t[0]===T_LNUMBER&&preg_match('/^(0|[1-9][0-9]*)$/D',$t[1])){$v=['integer',$sign.$t[1]];}
  elseif($t[0]===T_DNUMBER){$v=['float',$sign.$t[1]];}
  elseif($t[0]===T_STRING&&$sign===''&&in_array(strtolower($t[1]),['true','false','null'],true)){$v=['literal',strtolower($t[1])];}
  else throw new RuntimeException('Unsupported executable configuration expression');
  $this->i++;return [$v[0],$v[1],$start,$t[2]+strlen($t[1])-$start];
 }
 private function value($path,$depth){
  if($depth>64)throw new RuntimeException('Original configuration nesting exceeds bound');$id=json_encode($path,JSON_THROW_ON_ERROR);$t=$this->peek();
  if($t!==null&&$t[0]===T_ARRAY){
   $this->i++;$this->take('(');$keys=[];$seen=[];
   while(($this->peek()[0]??null)!==')'){
    $key=$this->scalar();if(!in_array($key[0],['string','integer'],true))throw new RuntimeException('Unsupported exported configuration key');
    $k=$key[1];if($key[0]==='integer'){if((string)(int)$k!==$k)throw new RuntimeException('Oversized original configuration key');$k=(int)$k;}
    $unique=(string)$k;if(isset($seen[$unique]))throw new RuntimeException('Duplicate original configuration key');$seen[$unique]=true;$keys[]=$k;
    $this->take(T_DOUBLE_ARROW);$this->value(array_merge($path,[$k]),$depth+1);
    if(($this->peek()[0]??null)===',')$this->i++;elseif(($this->peek()[0]??null)!==')')throw new RuntimeException('Missing original configuration separator');
   }
   $this->take(')');$this->arrays[$id]=$keys;return ['array',null];
  }
  $v=$this->scalar();$this->values[$id]=$v;return $v;
 }
 private function requireValue($path,$kind,$expected){$id=json_encode($path,JSON_THROW_ON_ERROR);$v=$this->values[$id]??null;if($v===null||$v[0]!==$kind||$v[1]!==$expected)throw new RuntimeException('Original configured endpoint or type differs');return $v;}
 function project($raw,$db,$redis){
  $replace=[];$path=['db','connection','default','host'];$v=$this->requireValue($path,'string','127.0.0.1:'.$db);$replace[]=[$v[2],$v[3],"'@original-shopping-database-endpoint@'"];
  $portId=json_encode(['db','connection','default','port']);if(isset($this->values[$portId])||isset($this->arrays[$portId]))throw new RuntimeException('Removed original database port key returned');
  $front=$this->arrays[json_encode(['cache','frontend'])]??null;if(!is_array($front)||count($front)===0)throw new RuntimeException('Original cache frontend configuration missing');
  foreach($front as$name){if(!is_string($name)||$name==='')throw new RuntimeException('Invalid original cache frontend');$base=['cache','frontend',$name,'backend_options'];$this->requireValue(array_merge($base,['server']),'string','127.0.0.1');$v=$this->requireValue(array_merge($base,['port']),'integer',(string)$redis);$replace[]=[$v[2],$v[3],'0'];}
  $save=$this->values[json_encode(['session','save'])]??null;if($save!==null&&$save[0]==='string'&&$save[1]==='redis'){$this->requireValue(['session','redis','host'],'string','127.0.0.1');$v=$this->requireValue(['session','redis','port'],'integer',(string)$redis);$replace[]=[$v[2],$v[3],'0'];}
  usort($replace,function($a,$b){return $b[0]<=>$a[0];});foreach($replace as$r)$raw=substr_replace($raw,$r[2],$r[0],$r[1]);return $raw;
 }
}
function shopping_navigation_search_config($raw,$search,$transport){
 if(strlen($raw)>1048576)throw new RuntimeException('Original search configuration exceeds bound');
 $expected=['network.host'=>'127.0.0.1','http.port'=>(string)$search,'transport.port'=>(string)$transport,'discovery.type'=>'single-node','node.processors'=>'2','path.data'=>'/usr/share/java/elasticsearch/data','path.logs'=>'/usr/share/java/elasticsearch/logs'];$seen=[];$out=[];
 foreach(explode("\n",$raw)as$line){$key=trim(explode(':',$line,2)[0]);if(array_key_exists($key,$expected)){if(isset($seen[$key])||$line!==$key.': '.$expected[$key])throw new RuntimeException('Original search control differs');$seen[$key]=true;if($key==='http.port')$line='http.port: @original-shopping-search-port@';elseif($key==='transport.port')$line='transport.port: @original-shopping-transport-port@';}$out[]=$line;}
 if(count($seen)!==count($expected))throw new RuntimeException('Missing original search controls');return implode("\n",$out);
}
"""
