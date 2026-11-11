"""Read the actual pinned image schema before implementing startup projection.

No database, website, original task, model or source permission is started.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
from test_admin_search_http import command
from test_admin_database_native import IMAGE_SHA

PROBE = r"""
$paths=['/var/www/magento2/vendor/magento/module-config/etc/db_schema.xml','/var/www/magento2/app/code/Magento/Config/etc/db_schema.xml'];
$found=[];foreach($paths as $path){if(is_file($path))$found[]=$path;}
if(count($found)!==1)throw new RuntimeException('One installed core config schema required');
$path=$found[0];if(filesize($path)>131072)throw new RuntimeException('Schema too large');$raw=file_get_contents($path);$x=simplexml_load_string($raw);$t=$x->xpath('//table[@name="core_config_data"]');if(count($t)!==1)throw new RuntimeException('Unique core config table required');
$columns=[];foreach($t[0]->column as $c){$row=[];foreach($c->attributes() as $k=>$v)$row[$k]=(string)$v;foreach($c->attributes('http://www.w3.org/2001/XMLSchema-instance') as $k=>$v)$row['xsi:'.$k]=(string)$v;$columns[]=$row;}
echo json_encode(['path'=>$path,'sha256'=>hash('sha256',$raw),'columns'=>$columns],JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
"""


def test_actual_pinned_startup_table_columns() -> None:
    result = subprocess.run(command(PROBE), capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode()
    facts = json.loads(result.stdout)
    names = [c["name"] for c in facts["columns"]]
    assert names in (
        ["config_id", "scope", "scope_id", "path", "value"],
        ["config_id", "scope", "scope_id", "path", "value", "updated_at"],
    ), names
    assert len(facts["sha256"]) == 64
    facts.update(
        image_sha256=IMAGE_SHA,
        actual_database_started=False,
        actual_website_started=False,
        models=0,
        raw_reply_sha256=hashlib.sha256(result.stdout).hexdigest(),
    )
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / "admin-navigation-runtime-config-schema.json"
    ).write_text(json.dumps(facts, indent=2) + "\n")
