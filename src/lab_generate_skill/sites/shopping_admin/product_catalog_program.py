"""Fixed private read-only product projection reused from admin-pilot-state.php.

Only the selected legacy product query/attributes/category names are retained;
no caller SQL, dynamic paths, credentials on argv or database mutation.
"""

PRODUCT_RECORDS_SQL = "SELECT p.entity_id,p.sku,n.value AS name,price.value AS price,special.value AS special_price,status.value AS status,country.value AS country_of_manufacture,stock.qty,stock.is_in_stock,stock.backorders,stock.use_config_backorders FROM catalog_product_entity p LEFT JOIN eav_attribute a ON a.entity_type_id=(SELECT entity_type_id FROM eav_entity_type WHERE entity_type_code='catalog_product') AND a.attribute_code='name' LEFT JOIN catalog_product_entity_varchar n ON n.entity_id=p.entity_id AND n.attribute_id=a.attribute_id AND n.store_id=0 LEFT JOIN eav_attribute pa ON pa.entity_type_id=(SELECT entity_type_id FROM eav_entity_type WHERE entity_type_code='catalog_product') AND pa.attribute_code='price' LEFT JOIN catalog_product_entity_decimal price ON price.entity_id=p.entity_id AND price.attribute_id=pa.attribute_id AND price.store_id=0 LEFT JOIN eav_attribute sa ON sa.entity_type_id=(SELECT entity_type_id FROM eav_entity_type WHERE entity_type_code='catalog_product') AND sa.attribute_code='special_price' LEFT JOIN catalog_product_entity_decimal special ON special.entity_id=p.entity_id AND special.attribute_id=sa.attribute_id AND special.store_id=0 LEFT JOIN eav_attribute sta ON sta.entity_type_id=(SELECT entity_type_id FROM eav_entity_type WHERE entity_type_code='catalog_product') AND sta.attribute_code='status' LEFT JOIN catalog_product_entity_int status ON status.entity_id=p.entity_id AND status.attribute_id=sta.attribute_id AND status.store_id=0 LEFT JOIN eav_attribute ca ON ca.entity_type_id=(SELECT entity_type_id FROM eav_entity_type WHERE entity_type_code='catalog_product') AND ca.attribute_code='country_of_manufacture' LEFT JOIN catalog_product_entity_varchar country ON country.entity_id=p.entity_id AND country.attribute_id=ca.attribute_id AND country.store_id=0 LEFT JOIN cataloginventory_stock_item stock ON stock.product_id=p.entity_id ORDER BY p.entity_id"
PRODUCT_ATTRIBUTES_SQL = "SELECT v.entity_id,a.attribute_code,v.value FROM catalog_product_entity_{$backend} v JOIN eav_attribute a ON a.attribute_id=v.attribute_id WHERE v.store_id=0 AND a.attribute_code IN ('name','description','short_description','meta_title','meta_description','url_key','include_in_menu','visibility','tax_class_id','custom_design','gift_message_available','special_from_date','special_to_date','news_from_date','news_to_date') ORDER BY v.entity_id"

PRODUCT_CATALOG_PHP = r"""
$pdo=null;
try {
foreach (['/state','/state/app','/state/app/app','/state/app/app/etc'] as $path) {
 if (is_link($path)||!is_dir($path)) throw new RuntimeException('Private instance required');
}
$config='/state/app/app/etc/env.php';$socket='/state/run/mysql.sock';
if (is_link($config)||!is_file($config)||is_link($socket)||filetype($socket)!=='socket') throw new RuntimeException('Original private config/socket required');
$id=$argv[1]??'';
if (!preg_match('/^[1-9][0-9]{0,9}$/D',$id)) throw new RuntimeException('Invalid product identity');
$id=(int)$id;
$env=include $config;$d=$env['db']['connection']['default'];
foreach (['dbname','username','password'] as $key) {
 if (!isset($d[$key])||!is_string($d[$key])||strpos($d[$key],chr(0))!==false) throw new RuntimeException('Invalid original database configuration');
}
if (!preg_match('/^[A-Za-z0-9_]+$/D',$d['dbname'])) throw new RuntimeException('Invalid database name');
$pdo=new PDO('mysql:unix_socket='.$socket.';dbname='.$d['dbname'].';charset=utf8mb4',$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$pdo->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
$pdo->exec('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY');
function rows($sql) { global $pdo;return $pdo->query($sql)->fetchAll(PDO::FETCH_ASSOC); }
$products=rows(__PRODUCT_QUERY__);
if (count($products)>1000001) throw new RuntimeException('Product count exceeds capture boundary');
$attributes=[];
foreach (['varchar','text','int','decimal','datetime'] as $backend) {
 $data=rows(__ATTRIBUTE_QUERY__);
 foreach ($data as $a) {
  if (array_key_exists($a['attribute_code'],$attributes[$a['entity_id']]??[])) throw new RuntimeException('Ambiguous product attribute');
  $attributes[$a['entity_id']][$a['attribute_code']]=$a['value'];
 }
}
$categories=rows("SELECT e.product_id,e.category_id,v.value AS name FROM catalog_category_product e JOIN catalog_category_entity c ON c.entity_id=e.category_id LEFT JOIN eav_attribute a ON a.entity_type_id=(SELECT entity_type_id FROM eav_entity_type WHERE entity_type_code='catalog_category') AND a.attribute_code='name' LEFT JOIN catalog_category_entity_varchar v ON v.entity_id=c.entity_id AND v.attribute_id=a.attribute_id AND v.store_id=0 ORDER BY e.category_id,e.product_id");
$names=[];
foreach ($categories as $row) $names[$row['product_id']][]=$row['name']??'';
$other=[];$target=null;$seen=[];
foreach ($products as $row) {
 $key=(string)$row['entity_id'];
 if (isset($seen[$key])) throw new RuntimeException('Duplicate product records');
 $seen[$key]=true;
 foreach (($attributes[$key]??[]) as $field=>$value) $row[$field]=$value;
 $row['category_names']=$names[$key]??[];sort($row['category_names']);ksort($row,SORT_STRING);
 if ((int)$key===$id) $target=$row; else $other[]=$row;
}
$flags=JSON_THROW_ON_ERROR|JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES;
$targetJson=$target===null?null:json_encode($target,$flags);
if ($targetJson!==null && strlen($targetJson)>262144) throw new RuntimeException('Target record exceeds capture boundary');
$digest=hash('sha256',json_encode($other,$flags));
$answer=['schema_version'=>'admin-product-catalog-state/1','projection'=>'legacy-admin-product-records-v1','product_id'=>$id,'store_id'=>0,'target_record_json'=>$targetJson,'other_product_count'=>count($other),'other_products_sha256'=>$digest];
$pdo->commit();$pdo=null;
echo json_encode($answer,$flags);
} catch (Throwable $error) {
 $primary=$error;
 if ($pdo!==null && $pdo->inTransaction()) {
  try {$pdo->rollBack();} catch (Throwable $cleanup) {fwrite(STDERR,'Rollback failure: '.get_class($cleanup).': '.$cleanup->getMessage().PHP_EOL);}
 }
 do {fwrite(STDERR,get_class($error).': '.$error->getMessage().PHP_EOL.$error->getTraceAsString().PHP_EOL);} while ($error=$error->getPrevious());
 exit(2);
}
""".replace("__PRODUCT_QUERY__", '"' + PRODUCT_RECORDS_SQL + '"').replace(
    "__ATTRIBUTE_QUERY__", '"' + PRODUCT_ATTRIBUTES_SQL + '"'
)
