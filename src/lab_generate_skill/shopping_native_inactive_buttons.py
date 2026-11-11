"""Do not render inactive native product payment blocks with side effects.

Magento's Braintree ProductPage calls getQuote before checking whether its
payment method is active. The native layout removal applies only after all
actual store scopes confirm the method is inactive. No PHP implementation,
payment configuration, quote row, browser action, or evaluator is modified.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

VERSION = 'native-inactive-braintree-product-layout-v1'
NATIVE_PATH = '/var/www/magento2/vendor/paypal/module-braintree-core/view/frontend/layout/catalog_product_view.xml'
NATIVE_SHA256 = '3a41f4a2c88d46dd92c740394796bf76b7648811d6dce2dc8bbf01acf63373b5'
BLOCK_NAMES = ('product.info.addtocart.paypalButton', 'product.info.addtocart.additional.paypalButton')
CLASS = 'PayPal\\Braintree\\Block\\Paypal\\ProductPage'

METHOD_STATE_PHP = r'''<?php
require '/var/www/magento2/app/bootstrap.php';
$bootstrap=\Magento\Framework\App\Bootstrap::create(BP,$_SERVER);
$om=$bootstrap->getObjectManager();
$om->get(\Magento\Framework\App\State::class)->setAreaCode('frontend');
$stores=$om->get(\Magento\Store\Model\StoreManagerInterface::class)->getStores(false);
$helper=$om->get(\Magento\Payment\Helper\Data::class);
$out=[];
foreach($stores as $store){
    $id=(int)$store->getId();
    $row=['store_id'=>$id];
    foreach(['braintree_paypal','banktransfer','checkmo'] as $code){
        $row[$code.'_active']=(bool)$helper->getMethodInstance($code)->isActive($id);
    }
    $out[]=$row;
}
echo json_encode(['version'=>'native-payment-method-all-store-state-v1','stores'=>$out]);
'''

def rewritten_layout(original):
    if not isinstance(original, bytes) or hashlib.sha256(original).hexdigest() != NATIVE_SHA256:
        raise ValueError('Actual pinned native Braintree product layout required')
    root = ET.fromstring(original)
    if root.tag != 'page' or len(root.findall('body')) != 1:
        raise ValueError('Native product layout body differs')
    body = root.find('body')
    for name in BLOCK_NAMES:
        blocks = [b for b in body.iter('block') if b.get('name') == name]
        if len(blocks) != 1 or blocks[0].get('class') != CLASS:
            raise ValueError('Native inactive product block identity differs')
        ET.SubElement(body, 'referenceBlock', {'name': name, 'remove': 'true'})
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

def validate_method_state(value):
    if not isinstance(value, dict) or value.get('version') != 'native-payment-method-all-store-state-v1':
        raise ValueError('Actual native all-store payment state required')
    stores = value.get('stores')
    if not isinstance(stores, list) or not stores:
        raise ValueError('Native store scopes are missing')
    seen = set()
    for row in stores:
        if not isinstance(row, dict) or set(row) != {'store_id','braintree_paypal_active','banktransfer_active','checkmo_active'}:
            raise ValueError('Complete native method state required')
        ident = row['store_id']
        if type(ident) is not int or ident <= 0 or ident in seen:
            raise ValueError('Unique actual frontend store scopes required')
        seen.add(ident)
        if any(type(row[name]) is not bool for name in ('braintree_paypal_active','banktransfer_active','checkmo_active')):
            raise ValueError('Actual native payment state must be boolean')
        if row['braintree_paypal_active']:
            raise ValueError('Active native PayPal product payments cannot be removed')
    return value

def prepare_native_layout(state, bare):
    original = subprocess.run(list(bare)+['php','-r','echo file_get_contents('+json.dumps(NATIVE_PATH)+');'],
                              check=True,capture_output=True,timeout=30).stdout
    patched = rewritten_layout(original)
    target = Path(state)/'inactive-native-product-payments.xml'
    with target.open('xb') as stream:
        stream.write(patched)
    target.chmod(0o600)
    report = {'version':VERSION,'native_layout_path':NATIVE_PATH,'native_layout_sha256':NATIVE_SHA256,
              'worker_layout_sha256':hashlib.sha256(patched).hexdigest(),
              'removed_inactive_native_blocks':list(BLOCK_NAMES),
              'payment_configuration_changed':False,'php_implementation_changed':False,
              'quote_cleanup_or_ignored_columns':False,'actual_native_inactivity_not_yet_verified':True}
    return ['--bind',str(target)+':'+NATIVE_PATH+':ro'],report

def confirm_native_inactive(site, report):
    source = Path(site.state)/'native-payment-method-state.php'
    with source.open('x') as stream:
        stream.write(METHOD_STATE_PHP)
    source.chmod(0o600)
    raw = site.command(['php','/state/'+source.name],capture_output=True,timeout=90).stdout
    state = validate_method_state(json.loads(raw))
    result = dict(report,actual_native_inactivity_not_yet_verified=False,
                  native_all_store_method_state=state,active_local_payment_methods_unchanged=True)
    destination = Path(site.logs)/'inactive-native-product-payments.json'
    destination.write_text(json.dumps(result,indent=2)+'\n')
    destination.chmod(0o600)
    return result
