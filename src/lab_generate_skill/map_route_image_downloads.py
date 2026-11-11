"""Terminal route-PNG evidence: actual download, owned receipt, full geometry.

The task permits varying bounds/scale. An independently captured route fixes
the geometry; a private re-render checks pixels only after these task checks.
Private re-renders are never inserted into the actor's browser or downloads.
"""
import hashlib,json
from pathlib import Path
from .io_utils import atomic_write_json
from .map_raster_artifact import decode,evaluate as compare_artifact
from .map_raster_request import export_byte_limit
from .map_route_image_request import check_request,native_line

VERSION='native-route-png-terminal-v1'


def evaluate(directory, references, receipts, *, render_reference, evidence_directory,
             integrity=True, runtime_error=None):
    checks={};artifacts=[]
    def result(status,reason):
        return dict(version=VERSION,status=status,reward=None if status=='unknown'else float(status=='success'),checks=checks,artifacts=artifacts,reason=reason)
    if runtime_error or integrity is not True:return result('unknown','Runtime or state integrity unavailable.')
    try:
        if not references:raise ValueError('Independent route reference missing')
        for ref in references:native_line(ref)
        if not isinstance(receipts,list) or any(not isinstance(r,dict)for r in receipts):raise ValueError('Renderer receipt capture unavailable')
        root=Path(directory);evidence=Path(evidence_directory)
        if root.is_symlink() or not root.is_dir():raise ValueError('Owned download directory missing')
        manifest=root/'downloads.json'
        if not manifest.exists():
            if list(root.iterdir()):raise ValueError('Download files lack recorder manifest')
            return result('failure','No image was downloaded.')
        if manifest.is_symlink()or manifest.stat().st_size>1024*1024:raise ValueError('Invalid download manifest')
        payload=json.loads(manifest.read_text())
        if payload.get('extra_browser_actions')!=0 or payload.get('task_success_inferred')is not False:
            raise ValueError('Unexpected recorder schema')
        rows=payload['downloads']
        if not isinstance(rows,list):raise ValueError('Download list missing')
        seen=set();cache={};winner=False;incomplete=False
        for row in rows:
            ident=row['download_id']
            if type(ident)is not int or ident<1 or ident in seen:raise ValueError('Duplicate/invalid download identity')
            seen.add(ident)
            if row['status'] in ('pending','failed'):
                incomplete=True;artifacts.append(dict(download_id=ident,status='unknown',reason='Download did not complete.'));continue
            if row['status']!='completed':raise ValueError('Unknown download state')
            path=root/('artifact-%04d.bin'%ident)
            if path.is_symlink()or path.stat().st_size!=row['bytes']:raise ValueError('Saved artifact changed')
            if path.stat().st_size>export_byte_limit('png'):
                artifacts.append(dict(download_id=ident,status='failure',reason='Not a bounded route PNG.'));continue
            body=path.read_bytes();digest=hashlib.sha256(body).hexdigest()
            if digest!=row['sha256']:raise ValueError('Download hash mismatch')
            try:decode(body)
            except (OSError,ValueError,TypeError):
                artifacts.append(dict(download_id=ident,status='failure',reason='Not a nonempty PNG.'));continue
            owned=[r for r in receipts if r.get('sha256')==digest and r.get('bytes')==len(body)]
            if not owned:
                incomplete=True;artifacts.append(dict(download_id=ident,status='unknown',reason='Renderer provenance missing.'));continue
            successes=[];detail=[]
            for receipt in owned:
                geometry=check_request(receipt['request'],references)
                detail.append(geometry)
                if not all(geometry.values()):continue
                public={k:receipt['request'][k]for k in ('bbox','scale','format','route')}
                key=hashlib.sha256(json.dumps(public,sort_keys=True).encode()).hexdigest()
                if key not in cache:
                    independent=render_reference(public);evidence.mkdir(parents=True,exist_ok=True)
                    (evidence/(key+'.png')).write_bytes(independent)
                    atomic_write_json(evidence/(key+'.json'),dict(request=public,sha256=hashlib.sha256(independent).hexdigest(),independent_route_bound=True,actor_browser_actions=0))
                    cache[key]=independent
                judgment=compare_artifact(body,receipt,public,cache[key])
                if judgment['status']=='unknown':incomplete=True
                successes.append(judgment['status']=='success');detail.append(judgment)
            passed=any(successes);winner|=passed
            artifacts.append(dict(download_id=ident,status='success'if passed else'failure',checks=detail))
        checks.update(verified_route_image=winner,private_render_requests=len(cache),recorded_downloads=len(rows))
        if incomplete:return result('unknown','Some download or native renderer evidence is incomplete.')
        return result('success'if winner else'failure','Checked saved PNG, owned rendering receipt, complete requested route and independent pixels.')
    except (OSError,ValueError,KeyError,TypeError,RuntimeError):
        return result('unknown','Download, reference or renderer bookkeeping is incomplete.')
