"""One original full snapshot inventory, data-only endpoint projection.

Reuse the original inventory algorithm, not another directory walker or restore
engine. Full raw content remains bound even for SQL/search/runtime sections.
"""

from ..snapshot_program import INVENTORY
from .navigation_file_projection import FILE_PROJECTION

FILE_CONTENTS = (
    FILE_PROJECTION
    + r"""
try {
if(count($argv)!==6)throw new RuntimeException('Original snapshot inventory and four ports required');
$ports=[];for($i=2;$i<=5;$i++){if(!ctype_digit($argv[$i])||(int)$argv[$i]<1024||(int)$argv[$i]>65535)throw new RuntimeException('Invalid original configured port');$ports[]=(int)$argv[$i];}if(count(array_unique($ports))!==4)throw new RuntimeException('Distinct original configured ports required');
$expected=json_decode($argv[1],true,16,JSON_THROW_ON_ERROR);$argv=['inventory','/snapshot/state','scan'];ob_start();
"""
    + INVENTORY
    + r"""
$raw=json_decode(ob_get_clean(),true,16,JSON_THROW_ON_ERROR);if($raw!==$expected)throw new RuntimeException('Original complete stopped snapshot differs');
$known=[];foreach($rows as$row)$known[$row[0]]=$row;
foreach(['mysql','etc','generated','var','search','search/config','search/data','tmp','var-tmp','mysql-tmp','redis','uploads','mail-outbox','nginx','native-static']as$p)if(($known[$p][1]??null)!=='directory')throw new RuntimeException('Required original snapshot directory missing');
foreach(['fastcgi_params','etc/env.php','search/config/elasticsearch.yml']as$p)if(($known[$p][1]??null)!=='file')throw new RuntimeException('Required original snapshot file missing');
function under($path,$root){return $path===$root||strpos($path,$root.'/')===0;}
function section($path){
 if(under($path,'mysql'))return 'database';if(under($path,'search/data'))return 'search';
 foreach(['tmp','var-tmp','mysql-tmp','redis','search/logs','search/tmp','nginx/client','nginx/proxy','nginx/fastcgi','var/cache','var/page_cache','var/session','var/log','var/locks','var/report','var/view_preprocessed','var/tmp']as$p)if(under($path,$p))return 'runtime';
 return 'included';
}
$parts=['included'=>[],'database'=>[],'search'=>[],'runtime'=>[]];$logical=[];
foreach($rows as$row){
 $part=section($row[0]);$parts[$part][]=$row;if($part!=='included')continue;$normal=$row;
 if(in_array($row[0],['etc/env.php','search/config/elasticsearch.yml'],true)){
  if($row[3]>1048576)throw new RuntimeException('Original configuration exceeds bound');$body=file_get_contents('/snapshot/state/'.$row[0]);if($body===false||strlen($body)!==$row[3]||hash('sha256',$body)!==$row[4])throw new RuntimeException('Original configuration changed after inventory');
  $body=$row[0]==='etc/env.php'?(new ShoppingNavigationConfig($body))->project($body,$ports[0],$ports[1]):shopping_navigation_search_config($body,$ports[2],$ports[3]);$normal[3]=strlen($body);$normal[4]=hash('sha256',$body);
 }
 $logical[]=$normal;
}
$summary=[];foreach($parts as$name=>$part){$f=0;$d=0;$b=0;foreach($part as$row){if($row[1]==='file'){$f++;$b+=$row[3];}else$d++;}$summary[$name]=['files'=>$f,'directories'=>$d,'bytes'=>$b,'raw_sha256'=>hash('sha256',json_encode($part,JSON_THROW_ON_ERROR))];}
echo json_encode(['schema_version'=>'shopping-navigation-file-contents/1','normalization'=>'original-shopping-category-files-and-endpoints-v1','inventory'=>$raw,'ports'=>$ports,'sections'=>$summary,'content_sha256'=>hash('sha256',json_encode($logical,JSON_THROW_ON_ERROR)),'snapshot_read_only'=>true,'configuration_executed'=>false],JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES);
}catch(Throwable $error){if(ob_get_level()>0)ob_end_clean();fwrite(STDERR,get_class($error).': '.$error->getMessage().PHP_EOL);exit(2);}
"""
)
