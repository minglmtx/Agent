"""Private pinned Git document lists, checked against independently rendered UI."""
import hashlib
import re
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt

from .site_database import select_rows


def validate(query):
    if query.get('list_scope', 'flat') not in ('flat', 'top_level'):
        raise ValueError('Unsupported document list scope')
    if query.get('fields') != {'items': 'record_set'} or query.get('record_fields') != {'items': {'name': 'string'}}:
        raise ValueError('Document list requires a typed name record set')
    if type(query.get('object_id')) is not int or query['object_id'] <= 0:
        raise ValueError('Invalid project identity')
    for key in ('head', 'object_sha'):
        if not re.fullmatch(r'[0-9a-f]{40}', query.get(key, '')):
            raise ValueError('Missing pinned Git object')
    path=query.get('document_path','')
    if path.startswith('/') or any(p in ('', '.', '..') for p in path.split('/')):
        raise ValueError('Invalid document path')
    if not isinstance(query.get('heading'),str) or not query['heading'].strip():
        raise ValueError('Missing document heading')
    if type(query.get('list_index')) is not int or query['list_index'] < 0:
        raise ValueError('Invalid document list index')


def records(labels):
    if not labels or any(not isinstance(s,str) or not s.strip() for s in labels):
        raise ValueError('Missing document list text')
    # Keep spelling and punctuation. Only collapse rendered whitespace.
    values=[' '.join(s.split()) for s in labels]
    if len(set(values))!=len(values):
        raise ValueError('Ambiguous duplicate document labels')
    return {'items':[{'name':s} for s in values]}


def markdown_values(text, query):
    """Parse the pinned file, never actor text or a list inferred from its answer."""
    soup=BeautifulSoup(MarkdownIt('commonmark').render(text),'html.parser')
    headings=[h for h in soup.find_all(re.compile(r'^h[1-6]$')) if h.get_text().strip()==query['heading']]
    if len(headings)!=1:raise ValueError('Missing or ambiguous reference heading')
    h=headings[0];lists=[]
    for node in h.next_siblings:
        if not getattr(node,'name',None):continue
        if re.fullmatch(r'h[1-6]',node.name) and int(node.name[1])<=int(h.name[1]):break
        if node.name in ('ul','ol'):lists.append(node)
    if query['list_index']>=len(lists):raise ValueError('Reference list missing')
    chosen=lists[query['list_index']]
    if chosen.find(['ul','ol']):
        if query.get('list_scope','flat')!='top_level':
            raise ValueError('Nested document lists require an explicit schema')
        # Explicitly requesting top-level library names excludes plugin lists.
        for nested in list(chosen.find_all(['ul','ol'])):
            if nested.parent is not None:nested.decompose()
    return records([li.get_text() for li in chosen.find_all('li',recursive=False)])


def reference(site, query):
    validate(query);ident=query['object_id']
    rows=select_rows(site,f"SELECT p.id,r.path FROM projects p JOIN routes r ON r.source_id=p.id AND r.source_type='Project' WHERE p.id={ident}")
    if len(rows)!=1 or rows[0]['path']!=query['project']:
        raise ValueError('Project route/reference mismatch')
    digest=hashlib.sha256(str(ident).encode()).hexdigest()
    repo='/var/opt/gitlab/git-data/repositories/@hashed/'+digest[:2]+'/'+digest[2:4]+'/'+digest+'.git'
    def git(*args):
        result=site.command(['/opt/gitlab/embedded/bin/git','--git-dir='+repo,*args],capture_output=True,text=True,timeout=40)
        if result.returncode:raise RuntimeError('Private Git document read failed')
        return result.stdout.rstrip('\n')
    head=git('rev-parse','HEAD')
    sha=git('rev-parse','HEAD:'+query['document_path'])
    if head!=query['head'] or sha!=query['object_sha']:
        raise ValueError('Document differs from pinned snapshot')
    text=git('show','HEAD:'+query['document_path'])
    return {'object_id':'gitlab_document:'+str(ident)+':'+query['document_path'],
            'values':markdown_values(text,query), 'evidence':{'head':head,'object_sha':sha,
            'text_sha256':hashlib.sha256(text.encode()).hexdigest()}}


READ_LIST = r'''q=>{
 const shown=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const files=[...document.querySelectorAll('.file-content')].filter(shown);
 const headings=files.flatMap(f=>[...f.querySelectorAll('h1,h2,h3,h4,h5,h6')]).filter(h=>shown(h)&&h.innerText.trim()===q.heading);
 if(headings.length!==1)throw Error('Missing or ambiguous rendered heading');
 const h=headings[0],lists=[];
 for(let e=h.nextElementSibling;e;e=e.nextElementSibling){
   if(/^H[1-6]$/.test(e.tagName)&&Number(e.tagName.slice(1))<=Number(h.tagName.slice(1)))break;
   if(['UL','OL'].includes(e.tagName)&&shown(e))lists.push(e);
 }
 const list=lists[q.list_index];if(!list)throw Error('Rendered list missing');
 if(list.querySelector('ul,ol')&&q.list_scope!=='top_level')throw Error('Unsupported nested rendered list');
 return [...list.children].filter(e=>e.tagName==='LI'&&shown(e)).map(e=>{
   if(q.list_scope!=='top_level')return e.innerText;
   const copy=e.cloneNode(true);copy.querySelectorAll('ul,ol').forEach(n=>n.remove());
   return copy.textContent;
 });
}'''


def ui_values(page,query):
    validate(query)
    if unquote(urlsplit(page.url).path).rstrip('/')!=query['reference_path'].rstrip('/'):
        raise ValueError('Unexpected document reference page')
    ids=page.locator('[data-project-id]').evaluate_all('es=>[...new Set(es.map(e=>e.getAttribute("data-project-id")))]')
    if not ids or any(i!=str(query['object_id'])for i in ids):
        raise ValueError('Rendered project identity mismatch')
    page.locator('.file-content').first.wait_for(state='visible',timeout=10000)
    return records(page.evaluate(READ_LIST,{'heading':query['heading'],'list_index':query['list_index'],
                                          'list_scope':query.get('list_scope','flat')}))
