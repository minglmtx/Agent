"""Original ordered core JSON hash plus private local mail metadata, no network."""

# Same ordered tables/columns and default json_encode bytes as the old site's
# fingerprint; hashing inside PHP avoids exporting all original account rows.
CORE_FINGERPRINT = r"""
$e=include "/var/www/magento2/app/etc/env.php";$d=$e["db"]["connection"]["default"];$h=explode(":",$d["host"]);
$p=new PDO("mysql:host=".$h[0].";port=".$h[1].";dbname=".$d["dbname"],$d["username"],$d["password"]);
$v=[];foreach(["catalog_product_entity"=>"entity_id,sku","customer_entity"=>"entity_id,email","sales_order"=>"entity_id,increment_id,status"]as$t=>$fields){$v[$t]=$p->query("SELECT ".$fields." FROM ".$t." ORDER BY entity_id")->fetchAll(PDO::FETCH_ASSOC);}
$raw=json_encode($v);if($raw===false)throw new RuntimeException('Native original core projection unavailable');echo hash('sha256',$raw);
"""

LOCAL_MAIL = r"""
$root='/state/mail-outbox';if(is_link($root)||!is_dir($root))throw new RuntimeException('Private mail profile missing');
$names=scandir($root);if($names===false)throw new RuntimeException('Unreadable private outbox');$rows=[];
foreach($names as$name){if($name==='.'||$name==='..')continue;$path=$root.'/'.$name;
 if(count($rows)>=256||is_link($path)||!is_file($path))throw new RuntimeException('Incomplete private mail inventory');
 $s=lstat($path);if($s===false||$s['nlink']!==1||$s['size']>5000000)throw new RuntimeException('Unsupported private message');
 $sha=hash_file('sha256',$path);if($sha===false)throw new RuntimeException('Unreadable private message');
 clearstatcache(true,$path);$after=lstat($path);if($after===false)throw new RuntimeException('Private message disappeared');
 foreach(['dev','ino','mode','nlink','size','mtime','ctime']as$key){if($s[$key]!==$after[$key])throw new RuntimeException('Private message changed');}
 $rows[]=['file'=>$name,'bytes'=>$s['size'],'sha256'=>$sha];
}
echo json_encode(['backend'=>'local_sendmail_capture_v1','messages'=>$rows,'external_delivery'=>false],JSON_THROW_ON_ERROR);
"""
