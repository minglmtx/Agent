"""Pinned installed help documents, with native rendered-body identity checks."""
import hashlib,re
from urllib.parse import urlsplit,unquote
from .document_sections import digest


def validate(spec):
    path=spec.get('source_path','')
    if (not isinstance(path,str)or not path.endswith('.md')or path.startswith('/')
        or any(p in ('','.','..')for p in path.split('/'))or '\x00'in path):
        raise ValueError('Explicit relative help source required')
    for key in ('source_sha256','body_sha256'):
        if not isinstance(spec.get(key),str)or not re.fullmatch('[0-9a-f]{64}',spec[key]):
            raise ValueError('Pinned help source and body hashes required')
    if not isinstance(spec.get('heading'),str)or not spec['heading'].strip():raise ValueError('Help document heading missing')


def verify_reference(site,spec):
    validate(spec)
    r=site.command(['cat','/opt/gitlab/embedded/service/gitlab-rails/doc/'+spec['source_path']],
                   capture_output=True,text=True,timeout=40)
    if r.returncode or hashlib.sha256(r.stdout.encode()).hexdigest()!=spec['source_sha256']:
        raise ValueError('Installed help source differs from the admitted version')


READ=r'''() => {
 const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 return {url:location.href,documents:[...document.querySelectorAll('.md')]
   .filter(e=>visible(e)&&!e.parentElement?.closest('.md')).map(e=>({
     headings:[...e.querySelectorAll('h1')].filter(visible).map(h=>h.innerText.trim()),
     text:e.innerText.trim()}))};
}'''


def read_help_document(page):return page.evaluate(READ)


def help_checks(spec,state):
    validate(spec)
    if not isinstance(state,dict)or not isinstance(state.get('url'),str)or not isinstance(state.get('documents'),list):
        raise ValueError('Missing native help document capture')
    expected='/help/'+spec['source_path'];actual=unquote(urlsplit(state['url']).path).rstrip('/')
    identity=actual in (expected,expected[:-3])
    matches=[]
    for row in state['documents']:
        if not isinstance(row,dict)or not isinstance(row.get('headings'),list)or not isinstance(row.get('text'),str):
            raise ValueError('Malformed help document capture')
        if row['headings']==[spec['heading']]:matches.append(row)
    return {'help_document_identity':identity and len(matches)==1,
            'help_document_content':len(matches)==1 and bool(matches[0]['text'])and digest(matches[0]['text'])==spec['body_sha256']}


FEEDBACK={'help_document_identity':'The requested native help document and its own heading are present.',
          'help_document_content':'The complete expected local help body is present; a heading or link alone is insufficient.'}
