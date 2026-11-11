"""Fixed read-only native probe, no Magento bootstrap/cache or caller SQL."""

PRODUCT_ABSENCE_PHP = r"""
try {
 $id=$argv[1]??'';
 if (!ctype_digit($id)||(int)$id<=0) throw new RuntimeException('Invalid original product ID');
 $file='/state/app/app/etc/env.php';$socket='/state/run/mysql.sock';
 if (is_link($file)||!is_file($file)||is_link($socket)||filetype($socket)!=='socket') throw new RuntimeException('Original private configuration/socket required');
 $e=include $file;$d=$e['db']['connection']['default'];
 $p=new PDO('mysql:unix_socket=/state/run/mysql.sock;dbname='.$d['dbname'],$d['username'],$d['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
 $q=$p->prepare('SELECT COUNT(*) FROM catalog_product_entity WHERE entity_id=?');$q->execute([(int)$id]);
 echo json_encode(['schema_version'=>'admin-product-absence/1','product_id'=>(int)$id,'absent'=>(int)$q->fetchColumn()===0],JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
} catch (Throwable $e) {fwrite(STDERR,get_class($e).': '.$e->getMessage().PHP_EOL);exit(2);}
"""
