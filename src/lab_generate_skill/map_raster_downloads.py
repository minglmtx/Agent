"""Terminal PNG checks over ordinary DownloadRecorder artifacts.

Private expected_request/reference must be bound to the declared initial page,
not to an actor-chosen download. Renderer receipts are owned service records.
No webpage requests, model calls, or goal-dependent browser actions occur here.
"""
import hashlib
import json
from pathlib import Path

from .map_raster_artifact import decode, evaluate
from .map_raster_request import normalize, export_byte_limit

VERSION='native-map-png-download-terminal-v1'
PDF_VERSION='native-map-pdf-download-terminal-candidate-v1'
MAX_BYTES=16*1024*1024


def artifact_backend(file_format):
    if file_format=='png':return decode,evaluate
    if file_format=='pdf':
        from .map_pdf_artifact import decode as decode_pdf,evaluate as evaluate_pdf
        return decode_pdf,evaluate_pdf
    raise ValueError('Explicit supported map artifact format required')


def evaluate_downloads(directory, *, expected_request, reference_body, receipts,
                       runtime_error=None, integrity=True, file_format='png'):
    decode_artifact,evaluate_artifact=artifact_backend(file_format)
    version=VERSION if file_format=='png' else PDF_VERSION
    matching_key='matching_native_'+file_format
    checks={'recording_available':False,'completed_download':False,
            matching_key:False}
    artifacts=[]

    def result(status,reason):
        return dict(version=version,status=status,
                    reward={'success':1.,'failure':0.,'unknown':None}[status],
                    checks=checks,artifacts=artifacts,reason=reason)

    if runtime_error or integrity is not True:
        return result('unknown','Runtime or state integrity is unavailable.')
    try:
        request=normalize(expected_request,allow_pdf=file_format=='pdf')
        if request['format']!=file_format:raise ValueError('Reference format differs from task')
        reference=decode_artifact(reference_body)
        if reference.size!=(request['width'],request['height']):
            raise ValueError('Reference dimensions changed')
        if not isinstance(receipts,list)or any(not isinstance(r,dict)for r in receipts):
            raise ValueError('Renderer receipt capture unavailable')
        root=Path(directory)
        if not root.is_dir()or root.is_symlink():
            raise ValueError('Recorder directory unavailable')
        manifest=root/'downloads.json'
        if manifest.is_symlink():raise ValueError('Recorder manifest is not owned')
        # DownloadRecorder creates the directory at startup, and writes its
        # manifest only on a real event. No manifest thus means no download.
        if not manifest.exists():
            if any(root.iterdir()):raise ValueError('Artifacts lack a recorder manifest')
            records=[]
        else:
            if manifest.stat().st_size>1024*1024:raise ValueError('Unbounded manifest')
            data=json.loads(manifest.read_text())
            if not isinstance(data,dict) or data.get('task_success_inferred')is not False or data.get('extra_browser_actions')!=0:
                raise ValueError('Unexpected recorder schema')
            records=data['downloads']
            if not isinstance(records,list):raise ValueError('Malformed downloads')
    except (ImportError,OSError,ValueError,TypeError,KeyError):
        return result('unknown','Initial reference or native download evidence is unavailable.')
    checks['recording_available']=True
    seen=set();capture_missing=False
    for row in records:
        try:
            ident=row['download_id']
            if type(ident)is not int or ident<=0 or ident in seen:
                raise ValueError('Invalid or repeated event identity')
            seen.add(ident)
            if row['status'] in ('pending','failed'):
                capture_missing=True
                artifacts.append(dict(download_id=ident,status='unknown',reason='Native download did not complete.'))
                continue
            if row['status']!='completed':raise ValueError('Unknown event status')
            path=root/('artifact-%04d.bin'%ident)
            if path.is_symlink()or path.stat().st_size!=row['bytes']:
                raise ValueError('Saved artifact changed')
            if path.stat().st_size>export_byte_limit(file_format):
                # PNG export is bounded at the native renderer; an unrelated
                # large download is a wrong artifact, not a reason to read it.
                artifacts.append(dict(download_id=ident,status='failure',reason='Not a bounded native '+file_format.upper()+' export.'))
                checks['completed_download']=True
                continue
            body=path.read_bytes();digest=hashlib.sha256(body).hexdigest()
            if digest!=row['sha256']:raise ValueError('Saved artifact hash changed')
            checks['completed_download']=True
            # A completed non-PNG attachment is an actor's wrong output.
            try:decode_artifact(body)
            except (OSError,ValueError,TypeError):
                artifacts.append(dict(download_id=ident,status='failure',reason='Not a nonempty native '+file_format.upper()+'.'))
                continue
            matching=[r for r in receipts if r.get('sha256')==digest and r.get('bytes')==len(body)]
            if not matching:
                # Valid PNG but no owned provenance: cannot distinguish a
                # wrong download from missing renderer capture.
                capture_missing=True
                artifacts.append(dict(download_id=ident,status='unknown',reason='Owned renderer provenance missing.'))
                continue
            judgments=[evaluate_artifact(body,r,expected_request,reference_body)for r in matching]
            success=any(j['status']=='success'for j in judgments)
            artifacts.append(dict(download_id=ident,status='success'if success else'failure',
                                  checks=next((j['checks']for j in judgments if j['status']=='success'),judgments[0]['checks'])))
            checks[matching_key]|=success
        except (OSError,ValueError,TypeError,KeyError):
            # Broken recording cannot silently disappear from a final reward.
            return result('unknown','Saved download bookkeeping is inconsistent.')
    if checks[matching_key]:
        return result('success','An actual saved native '+file_format.upper()+' matches the declared initial reference.')
    if capture_missing:return result('unknown','Download or renderer capture did not complete.')
    return result('failure','No completed download satisfies the declared map export.')


def feedback(judgment):
    if judgment.get('version')not in (VERSION,PDF_VERSION):raise ValueError('Native map artifact terminal judgment required')
    return dict(status=judgment['status'],reward=judgment['reward'],reason=judgment['reason'],
                checks=[dict(condition=k,passed=v)for k,v in judgment['checks'].items()],
                private_reference_values_provided=False,action_sequence_provided=False)
