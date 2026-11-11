"""Native CMS policy readouts, independent of actor wording or visited steps."""
import hashlib
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from .site_database import select_rows

IDENTIFIER='privacy-policy-cookie-restriction-mode'
KINDS={'collected_types':('What we collect',{'items':'record_set'}),
       'control_policy':('Controlling your personal information',{'policy_text':'string'})}


def normalize(text):return ' '.join(text.split())


def rendered_text(node):
    # Inline links preserve punctuation; block/list boundaries create spaces.
    for br in node.find_all('br'):br.replace_with(' ')
    if node.name in ('ul','ol'):
        text=' '.join(rendered_text(li)for li in node.find_all('li',recursive=False))
    else:text=node.get_text()
    if '{{'in text:raise ValueError('Policy text contains unresolved CMS directives')
    return normalize(text)


def validate(q):
    if q.get('family')!='shopping_policy' or q.get('kind')not in KINDS:
        raise ValueError('Unsupported policy query')
    heading,fields=KINDS[q['kind']]
    if q.get('reference_path')!='/'+IDENTIFIER or q.get('fields')!=fields:
        raise ValueError('Unsupported native policy scope')
    if q['kind']=='collected_types' and q.get('record_fields')!={'items':{'name':'string'}}:
        raise ValueError('Explicit policy item schema required')
    return heading


def section_values(html,q):
    heading=validate(q);soup=BeautifulSoup(html,'html.parser')
    hs=[h for h in soup.find_all(re.compile('^h[1-6]$'))if normalize(h.get_text(' ',strip=True))==heading]
    if len(hs)!=1:raise ValueError('Native policy heading absent or ambiguous')
    h=hs[0];parts=[]
    for node in h.next_siblings:
        if not getattr(node,'name',None):continue
        if re.fullmatch('h[1-6]',node.name) and int(node.name[1])<=int(h.name[1]):break
        parts.append(node)
    if q['kind']=='collected_types':
        lists=[n for n in parts if n.name in ('ul','ol')]
        if len(lists)!=1 or lists[0].find(['ul','ol']):raise ValueError('Policy type list missing or nested')
        values=[rendered_text(li)for li in lists[0].find_all('li',recursive=False)]
        if not values or any(not v for v in values)or len(values)!=len(set(values)):
            raise ValueError('Incomplete policy type list')
        return {'items':[{'name':v}for v in values]}
    text=normalize(' '.join(rendered_text(n)for n in parts))
    if not text:raise ValueError('Policy section is empty')
    return {'policy_text':text}


def reference(site,q):
    validate(q)
    pages=select_rows(site,"SELECT page_id,identifier,title,content,is_active FROM cms_page WHERE identifier='"+IDENTIFIER+"' ORDER BY page_id")
    if getattr(site,'logs',None) is not None:
        from .io_utils import atomic_write_json
        atomic_write_json(site.logs/'policy-reference.json',{'pages':pages})
    if len(pages)!=1 or not pages[0]['is_active']:raise ValueError('Unique active native policy page missing')
    row=pages[0];html=row['content']
    # Attribute-only URL directives do not alter copied text. Text-generating
    # directives in the selected section are rejected by rendered_text.
    return {'object_id':'shopping-policy:'+str(row['page_id'])+':'+q['kind'],
            'values':section_values(html,q),
            'source_state':{'page_id':row['page_id'],'identifier':row['identifier'],'title':row['title'],
                            'content_sha256':hashlib.sha256(html.encode()).hexdigest(),'is_active':row['is_active']}}


READ=r'''heading=>{
 const shown=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const hs=[...document.querySelectorAll('main h1,main h2,main h3,main h4,main h5,main h6')]
   .filter(e=>shown(e)&&e.innerText.trim()===heading);
 if(hs.length!==1)throw Error('Native policy heading absent or ambiguous');
 const h=hs[0],nodes=[];
 for(let n=h.nextElementSibling;n;n=n.nextElementSibling){
   if(/^H[1-6]$/.test(n.tagName)&&Number(n.tagName.slice(1))<=Number(h.tagName.slice(1)))break;
   if(shown(n))nodes.push(n);
 }
 return {text:nodes.map(n=>n.innerText).join(' '),
  lists:nodes.filter(n=>['UL','OL'].includes(n.tagName)).map(n=>({nested:!!n.querySelector('ul,ol'),
    items:[...n.children].filter(e=>e.tagName==='LI'&&shown(e)).map(e=>e.innerText)}))};
}'''


def ui_values(page,q):
    heading=validate(q)
    if urlsplit(page.url).path.rstrip('/')!='/'+IDENTIFIER:raise ValueError('Unexpected policy URL')
    observed=page.evaluate(READ,heading)
    if q['kind']=='collected_types':
        lists=observed['lists']
        if len(lists)!=1 or lists[0]['nested']:raise ValueError('Policy list unavailable')
        names=[normalize(s)for s in lists[0]['items']]
        if not names or len(names)!=len(set(names))or any(not s for s in names):raise ValueError('Incomplete visible policy list')
        return {'items':[{'name':s}for s in names]}
    text=normalize(observed['text'])
    if not text:raise ValueError('Visible policy section empty')
    return {'policy_text':text}
