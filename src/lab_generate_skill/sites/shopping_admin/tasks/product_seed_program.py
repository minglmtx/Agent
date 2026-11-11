"""Fixed Magento create-only fixture and measured record; no goal text supplied."""

PRODUCT_SEED_PHP = r"""
try {
if (!is_dir('/state/app') || !is_dir('/state/mysql')) throw new RuntimeException('Private instance required');
$in=json_decode($argv[1],true,512,JSON_THROW_ON_ERROR);
if (!in_array($in['operation'],['initialize','inspect'],true) || !is_int($in['product_id']) || $in['product_id']<=0) throw new RuntimeException('Invalid product operation');
require '/var/www/magento2/app/bootstrap.php';
$bootstrap=\Magento\Framework\App\Bootstrap::create(BP,$_SERVER);
$om=$bootstrap->getObjectManager();
$om->get(\Magento\Framework\App\State::class)->setAreaCode('adminhtml');
$resource=$om->get(\Magento\Framework\App\ResourceConnection::class);$db=$resource->getConnection();
$repo=$om->get(\Magento\Catalog\Api\ProductRepositoryInterface::class);
if ($in['operation']==='initialize') {
 $v=$in['values'];
 if ($db->fetchOne($db->select()->from($resource->getTableName('catalog_product_entity'),'entity_id')->where('sku = ?',$v['sku'])->orWhere('entity_id = ?',$in['product_id']))) throw new RuntimeException('Original SKU or expected ID already exists; no overwrite');
 $names=$om->create(\Magento\Catalog\Model\ResourceModel\Product\Collection::class)->addAttributeToFilter('name',$v['name']);
 if ($names->getSize()) throw new RuntimeException('Fixture name already exists');
 $next=$db->fetchOne('SELECT AUTO_INCREMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=?',[$resource->getTableName('catalog_product_entity')]);
 if ((int)$next!==$in['product_id']) throw new RuntimeException('Original expected next product ID differs');
 $taxes=$db->fetchCol($db->select()->from($resource->getTableName('tax_class'),'class_id')->where('class_name = ?',$v['tax_label'])->where('class_type = ?','PRODUCT'));
 if (count($taxes)!==1) throw new RuntimeException('Tax class missing or ambiguous');
 $product=$om->get(\Magento\Catalog\Model\ProductFactory::class)->create();
 $product->setStoreId(0)->setTypeId('simple')->setAttributeSetId(4)->setSku($v['sku'])
 ->setName($v['name'])->setPrice((float)$v['price'])->setTaxClassId((int)$taxes[0])
 ->setVisibility(1)->setStatus(1)->setWeight(0)->setWebsiteIds([1])->setShortDescription('')
 ->setUrlKey('gobrowse-pilot-'.strtolower(preg_replace('/[^a-zA-Z0-9]+/','-',$v['name'])))
 ->setStockData(['use_config_manage_stock'=>1,'manage_stock'=>1,'is_in_stock'=>0,'qty'=>0]);
 $saved=$repo->save($product);
 if ((int)$saved->getId()!==$in['product_id']) throw new RuntimeException('Saved product ID differs; isolate partial state');
}
$product=$repo->getById($in['product_id'],false,0,true);
$stock=$om->get(\Magento\CatalogInventory\Api\StockRegistryInterface::class)->getStockItem($product->getId());
$websites=array_map('intval',$product->getWebsiteIds());sort($websites);
$categories=array_map('intval',$product->getCategoryIds());sort($categories);
echo json_encode([
 'schema_version'=>'admin-product-state/1','product_id'=>(int)$product->getId(),'store_id'=>0,
 'sku'=>(string)$product->getSku(),'name'=>(string)$product->getName(),
 'price'=>(string)$product->getPrice(),'qty'=>(string)$stock->getQty(),'weight'=>(string)$product->getWeight(),
 'tax_class_id'=>(int)$product->getTaxClassId(),
 'tax_class_label'=>(string)$db->fetchOne($db->select()->from($resource->getTableName('tax_class'),'class_name')->where('class_id = ?',$product->getTaxClassId())->where('class_type = ?','PRODUCT')),
 'visibility'=>(int)$product->getVisibility(),
 'status'=>(int)$product->getStatus(),'is_in_stock'=>(bool)$stock->getIsInStock(),
 'website_ids'=>$websites,'category_ids'=>$categories,'url_key'=>(string)$product->getUrlKey(),
 'type_id'=>(string)$product->getTypeId(),'short_description'=>$product->getShortDescription(),
 'description'=>$product->getDescription()
],JSON_THROW_ON_ERROR|JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);
} catch (Throwable $error) {
 do {
  fwrite(STDERR,get_class($error).': '.$error->getMessage().PHP_EOL.$error->getTraceAsString().PHP_EOL);
 } while ($error=$error->getPrevious());
 exit(2);
}
"""
