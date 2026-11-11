"""Publish missing installed native assets in a worker-private module binding.

Retains original published bytes, including preprocessed assets. Only missing
files from the same installed Magento frontend module may be added. No injected
HTML, controls, template modifications or remote source is accepted.
"""
import json,re,subprocess
from pathlib import Path
MODULES={'Magento_OfflinePayments':'magento/module-offline-payments'}
PREPARE=r'''$args=json_decode($argv[1],true,512,JSON_THROW_ON_ERROR);$out=[];
foreach($args as$module=>$vendor){
 $source='/var/www/magento2/vendor/'.$vendor.'/view/frontend/web';$published='/var/www/magento2/pub/static/frontend/Magento/blank/en_US/'.$module;$target='/state/native-static/'.$module;
 if(!is_dir($source)||!is_dir($published))throw new RuntimeException('Installed native module/published namespace missing');
 if(file_exists($target))throw new RuntimeException('Never reuse a mutable native asset staging directory');
 mkdir($target,0700,true);$original=[];$added=[];
 $copy=function($tree,$extra)use($target,&$original,&$added){
  $iter=new RecursiveIteratorIterator(new RecursiveDirectoryIterator($tree,FilesystemIterator::SKIP_DOTS));
  foreach($iter as$file){if(!$file->isFile())continue;$rel=substr($file->getPathname(),strlen($tree)+1);if(strpos($rel,'..')!==false||substr($rel,0,1)==='/')throw new RuntimeException('Unsafe native asset path');$dest=$target.'/'.$rel;
   $bytes=file_get_contents($file->getPathname());if($bytes===false)throw new RuntimeException('Unreadable installed native asset');$sha=hash('sha256',$bytes);
   if(!$extra||!file_exists($dest)){if(!is_dir(dirname($dest)))mkdir(dirname($dest),0700,true);if(file_put_contents($dest,$bytes)!==strlen($bytes))throw new RuntimeException('Native asset copy incomplete');}
   if($extra&&isset($original[$rel])){if(hash_file('sha256',$dest)!==$original[$rel])throw new RuntimeException('Original published asset overwritten');continue;}
   if(hash_file('sha256',$dest)!==$sha)throw new RuntimeException('Native staged bytes differ');
   if($extra)$added[$rel]=$sha;else$original[$rel]=$sha;
  }
 };
 $copy($published,false);$copy($source,true);ksort($original);ksort($added);
 $out[$module]=['installed_source'=>$source,'original_published_namespace'=>$published,'original_published_sha256'=>$original,'added_installed_sha256'=>$added,'native_bytes_only'=>true,'original_published_bytes_unchanged'=>true,'external_source_used'=>false];
}echo json_encode($out,JSON_THROW_ON_ERROR);'''

def prepare_native_assets(state,bare,*,modules=tuple(MODULES)):
 if not isinstance(state,Path)or state.is_symlink()or not state.is_dir():raise ValueError('Private regular native state required')
 if not modules or len(set(modules))!=len(modules)or any(m not in MODULES for m in modules):raise ValueError('Explicit installed native module allowlist required')
 payload={m:MODULES[m]for m in modules};r=subprocess.run(bare+['php','-r',PREPARE,json.dumps(payload)],check=True,capture_output=True,text=True,timeout=60);evidence=json.loads(r.stdout)
 if set(evidence)!=set(modules):raise ValueError('Incomplete installed native module publication')
 bindings=[]
 for m in modules:
  row=evidence[m]
  if row.get('native_bytes_only')is not True or row.get('original_published_bytes_unchanged')is not True or row.get('external_source_used')is not False or not row.get('original_published_sha256')or not row.get('added_installed_sha256'):raise ValueError('Native asset provenance incomplete')
  if any(not re.fullmatch('[0-9a-f]{64}',h)for field in('original_published_sha256','added_installed_sha256')for h in row[field].values()):raise ValueError('Invalid native asset digest')
  bindings.extend(['--bind',str(state/'native-static'/m)+':'+row['original_published_namespace']+':ro'])
 return bindings,evidence
