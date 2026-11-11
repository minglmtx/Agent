"""Persist new native MIME bytes privately, inside the existing task archive."""
import base64
import hashlib
from pathlib import Path

def capture_new_messages(before, current, outbox):
    if current.get('backend')!='local_sendmail_capture_v1' or current.get('external_delivery')is not False:
        raise ValueError('Local native sink required')
    known={r['file']for r in before['messages']}
    result={}
    for metadata in current['messages']:
        name=metadata['file']
        if not isinstance(name,str)or Path(name).name!=name or name in ('.','..'):
            raise ValueError('Native local message filename required')
        if name in known:
            continue
        if name in result:
            raise ValueError('Duplicate native message')
        path=Path(outbox)/name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Regular native message required')
        body=path.read_bytes()
        if metadata!={'file':name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}:
            raise ValueError('Native MIME bytes differ from terminal metadata')
        result[name]={'metadata':dict(metadata),'mime_base64':base64.b64encode(body).decode('ascii')}
    return {'version':'private-native-mail-content-v1','actor_input':False,'messages':result}
