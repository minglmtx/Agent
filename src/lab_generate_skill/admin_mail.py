"""Read isolated captured mail. Neither an SMTP client nor a sender."""
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
import hashlib
from pathlib import Path

def read_mail(directory):
    directory=Path(directory)
    if directory.is_symlink():raise ValueError('Mail spool must not be a symlink')
    rows=[]
    for path in sorted(directory.glob('*.eml')):
        if path.is_symlink() or not path.is_file() or path.stat().st_size>5_000_000:raise ValueError('Invalid captured message')
        raw=path.read_bytes();message=BytesParser(policy=policy.default).parsebytes(raw)
        parts=[p for p in message.walk() if p.get_content_type() in ('text/plain','text/html') and p.get_content_disposition()!='attachment']
        rows.append({'entity_id':path.name,'sha256':hashlib.sha256(raw).hexdigest(),
                     'recipients':sorted({a.casefold() for _,a in getaddresses(message.get_all('to',[])+message.get_all('cc',[])+message.get_all('bcc',[]))}),
                     'subject':str(message.get('Subject','')),'body':'\n'.join(p.get_content() for p in parts)})
    return rows

def delivered(before,after,recipient,required_text):
    ids={r['entity_id'] for r in before}
    return any(r['entity_id'] not in ids and recipient.casefold() in r['recipients'] and
               all(text.casefold() in (r['subject']+'\n'+r['body']).casefold() for text in required_text)
               for r in after)
