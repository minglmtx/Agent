"""Verify persisted product media and local upload resources, without visual judging."""
from pathlib import Path
import hashlib

def hash_media(rows,root,product_ids):
    root=Path(root).resolve()
    for row in rows:
        if str(row['product_id']) not in product_ids:continue
        relative=str(row['file']).lstrip('/')
        path=root/relative
        if path.is_symlink() or '..' in Path(relative).parts:raise ValueError('Invalid media file path')
        path.resolve().relative_to(root)
        row['file_exists']=path.is_file()
        row['sha256']=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def checks(spec,binding,before,after):
    pid=str(binding['record_id']);initial=before['records']['media'];final=after['records']['media']
    old=[r for r in initial if str(r['product_id'])==pid];new=[r for r in final if str(r['product_id'])==pid]
    unrelated=lambda rows:[r for r in rows if str(r['product_id'])!=pid]
    out={'other_product_media_unchanged':unrelated(initial)==unrelated(final)}
    if spec['operation']=='upload':
        oldids={r['entity_id'] for r in old}
        out['new_file_saved_on_target']=any(r['entity_id'] not in oldids and r.get('file_exists') and r.get('sha256')==spec['asset_sha256'] for r in new)
    elif spec['operation']=='remove_all':out['existing_images_removed']=bool(old) and not new
    else:raise ValueError('Unsupported media operation')
    return out
