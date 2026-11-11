"""Read-only layout discovery before any second-site extraction or native service."""

import re
from typing import Any
from lab_generate_skill.adapters.processes.wire_json import json_object

PROBE = r"""
$paths=[
 'database'=>'/var/lib/mysql',
 'application'=>'/var/www/magento2',
 'configuration'=>'/var/www/magento2/app/etc/env.php',
 'generated'=>'/var/www/magento2/generated',
 'search_config'=>'/usr/share/java/elasticsearch/config',
 'search_data'=>'/usr/share/java/elasticsearch/data',
 'module_source'=>'/var/www/magento2/vendor/magento/module-offline-payments/view/frontend/web',
 'module_published'=>'/var/www/magento2/pub/static/frontend/Magento/blank/en_US/Magento_OfflinePayments'
];
$out=[];foreach($paths as $name=>$path){$out[$name]=file_exists($path)&&is_readable($path);}
$sources=[];foreach([
 'vendor/magento/module-sales/Model/Order/Status/History.php',
 'vendor/magento/module-sales/Model/ResourceModel/Order/Status/History.php',
 'vendor/magento/module-sales/view/frontend/templates/order/order_comments.phtml'
] as $file){$path='/var/www/magento2/'.$file;$sources[$file]=is_file($path)?hash_file('sha256',$path):null;}
echo json_encode(['schema_version'=>'shopping-image-layout-probe/1','php'=>PHP_VERSION,
 'pdo_mysql'=>extension_loaded('pdo_mysql'),'paths'=>$out,'order_sources'=>$sources,
 'native_services_started'=>false,'credentials_read'=>false],JSON_THROW_ON_ERROR);
"""
PATH_KEYS = frozenset(
    {
        "database",
        "application",
        "configuration",
        "generated",
        "search_config",
        "search_data",
        "module_source",
        "module_published",
    }
)
SOURCE_KEYS = frozenset(
    {
        "vendor/magento/module-sales/Model/Order/Status/History.php",
        "vendor/magento/module-sales/Model/ResourceModel/Order/Status/History.php",
        "vendor/magento/module-sales/view/frontend/templates/order/order_comments.phtml",
    }
)


def parse_probe(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 16384:
        raise ValueError("Shopping layout probe outside byte boundary")
    value = json_object(raw)
    if (
        set(value)
        != {
            "schema_version",
            "php",
            "pdo_mysql",
            "paths",
            "order_sources",
            "native_services_started",
            "credentials_read",
        }
        or value["schema_version"] != "shopping-image-layout-probe/1"
    ):
        raise ValueError("Shopping layout probe schema differs")
    if (
        type(value["php"]) is not str
        or not value["php"]
        or type(value["pdo_mysql"]) is not bool
        or value["native_services_started"] is not False
        or value["credentials_read"] is not False
    ):
        raise ValueError("Shopping layout probe scalar/effect fields differ")
    paths, sources = value["paths"], value["order_sources"]
    if (
        type(paths) is not dict
        or set(paths) != PATH_KEYS
        or any(type(v) is not bool for v in paths.values())
    ):
        raise ValueError("Shopping layout paths differ")
    if (
        type(sources) is not dict
        or set(sources) != SOURCE_KEYS
        or any(
            v is not None
            and (type(v) is not str or re.fullmatch("[0-9a-f]{64}", v) is None)
            for v in sources.values()
        )
    ):
        raise ValueError("Shopping native source identity differs")
    # Missing prerequisites are retained false/null, never converted to ready.
    return value
