"""Private complete-article identity checks for native commit diff pages.

A filename or commit title alone is insufficient. Only complete contiguous
rendered lines with the same article title and body are equivalent. Frontmatter
metadata such as the description is not article prose; no semantic LLM is used.
"""
import hashlib,re
from urllib.parse import urlsplit,unquote
import yaml

READ_DIFFS=r'''() => {
 const visible=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
 return [...document.querySelectorAll('.diff-file[data-blob-diff-path]')].filter(visible).slice(0,64).map(e=>({
   blob_diff_path:e.getAttribute('data-blob-diff-path'),
   lines:[...e.querySelectorAll('tr.line_holder')].filter(visible).slice(0,2000).map(row=>({
     number:row.querySelector('td.new_line')?.getAttribute('data-linenumber')||null,
     text:row.querySelector('td.line_content > span.line')?.textContent??null
   }))
 }));
}'''


def article_identity(text):
    if not isinstance(text,str):raise ValueError('Missing article text')
    text=text.replace('\r\n','\n')
    match=re.fullmatch(r'---\n(.*?)\n---\n(.*)',text,re.S)
    if not match:raise ValueError('Expected native Markdown frontmatter article')
    metadata=yaml.safe_load(match[1]);body=match[2].strip()
    if not isinstance(metadata,dict) or not isinstance(metadata.get('title'),str) or not metadata['title'].strip() or not body:
        raise ValueError('Missing article title/body')
    return {'format':'markdown-frontmatter-title-body-v1','title':metadata['title'].strip(),
            'body_sha256':hashlib.sha256(body.encode()).hexdigest()}


def equivalent_article(spec,state,current_url):
    """False for missing/wrong/partial content; never interpret actor free text."""
    expected=spec.get('document_equivalence')
    if not expected:return False
    if expected.get('format')!='markdown-frontmatter-title-body-v1':raise ValueError('Unsupported equivalence protocol')
    if not isinstance(state,dict) or str(spec['project_id']) not in state.get('project_ids',[]):return False
    if state.get('loading') is not False or state.get('wait_status')!='ready':return False
    path=unquote(urlsplit(current_url).path)
    match=re.fullmatch(re.escape('/'+spec['project']+'/-/commit/')+r'([0-9a-f]{40})/?',path)
    if not match:return False
    target='/'+spec['project']+'/-/blob/'+match[1]+'/'+spec['path']+'/diff'
    entries=[r for r in state.get('diff_files',[]) if r.get('blob_diff_path')==target]
    if len(entries)!=1:return False
    rows=entries[0].get('lines')
    if not isinstance(rows,list) or not rows:return False
    if any(not isinstance(r,dict) or not isinstance(r.get('text'),str) or r.get('number')!=str(i) for i,r in enumerate(rows,1)):return False
    text='\n'.join(r['text'] for r in rows)
    try:return article_identity(text)==expected
    except (ValueError,yaml.YAMLError):return False
