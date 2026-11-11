"""Local sendmail capture for isolated website diagnostics, without delivery."""
import hashlib
import shlex
from pathlib import Path


def prepare(state, *, container_root='/state'):
    state=Path(state);outbox=state/'mail-outbox';outbox.mkdir(mode=0o700,exist_ok=False)
    # The image's mktemp requires the X template at the end. Do not rely
    # on GNU's inferred suffix extension; mail files need no extension.
    target=str(Path(container_root)/'mail-outbox'/'message-XXXXXXXX')
    script=state/'capture-mail.sh'
    script.write_text('#!/bin/sh\nset -eu\numask 077\n'
        'message=$(mktemp '+shlex.quote(target)+')\n'
        'if cat > "$message"; then exit 0; fi\n'
        'rm -f -- "$message"\nexit 1\n')
    script.chmod(0o700)
    return outbox


def evidence(directory):
    """Metadata only. Message bodies and recipient addresses stay private."""
    rows=[]
    for path in sorted(Path(directory).glob('message-*')):
        payload=path.read_bytes()
        rows.append({'file':path.name,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()})
    return {'backend':'local_sendmail_capture_v1','messages':rows,'external_delivery':False}
