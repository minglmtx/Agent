"""Native Shopping CMS sections, independently pinned to stored page content."""
import hashlib
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from .document_sections import READ, digest, section_checks
from .shopping_policy_query import rendered_text
from .site_database import select_rows

# Preserve the existing GitLab reader verbatim; select the native CMS column.
READ_CMS = '() => ({url:location.href,sections:(' + READ.replace("'.file-content'", "'main .column.main'") + ')()})'


def section_text(html, heading):
    soup=BeautifulSoup(html,'html.parser')
    matches=[h for h in soup.find_all(re.compile('^h[1-6]$')) if ' '.join(h.get_text(' ',strip=True).split())==heading]
    if len(matches)!=1:raise ValueError('Stored CMS section missing or ambiguous')
    h=matches[0];parts=[]
    for node in h.next_siblings:
        if not getattr(node,'name',None):continue
        if re.fullmatch('h[1-6]',node.name) and int(node.name[1])<=int(h.name[1]):break
        if node.name=='table':
            if node.find('table'):raise ValueError('Nested CMS tables require a separate reader')
            parts.append(' '.join(rendered_text(cell)for row in node.find_all('tr')for cell in row.find_all(['th','td'],recursive=False)))
        else:parts.append(rendered_text(node))
    text=' '.join(' '.join(parts).split())
    if not text:raise ValueError('Stored CMS section empty')
    return text


def validate(spec):
    if (not isinstance(spec,dict) or set(spec)!={'identifier','page_id','content_sha256','heading','body_sha256'}
        or not isinstance(spec['identifier'],str)or not re.fullmatch(r'[a-z0-9_-]+',spec['identifier'])
        or type(spec['page_id'])is not int or spec['page_id']<=0
        or not isinstance(spec['heading'],str)or not spec['heading'].strip()
        or any(not isinstance(spec[k],str)or not re.fullmatch('[0-9a-f]{64}',spec[k])for k in ('content_sha256','body_sha256'))):
        raise ValueError('Invalid independently pinned CMS section')


def verify_reference(site,spec):
    validate(spec)
    rows=select_rows(site,"SELECT page_id,identifier,content,is_active FROM cms_page WHERE page_id="+str(spec['page_id']))
    if (len(rows)!=1 or rows[0]['identifier']!=spec['identifier']or not rows[0]['is_active']
        or hashlib.sha256(rows[0]['content'].encode()).hexdigest()!=spec['content_sha256']
        or digest(section_text(rows[0]['content'],spec['heading']))!=spec['body_sha256']):
        raise ValueError('CMS page or requested section differs from pinned native reference')


def read_cms_section(page):
    return page.evaluate(READ_CMS)


def checks(spec,state,*,issued_request=None):
    validate(spec)
    if not isinstance(state,dict)or not isinstance(state.get('url'),str):raise ValueError('Missing native CMS section capture')
    if urlsplit(state['url']).path.rstrip('/')!='/'+spec['identifier']:
        return {'cms_document_identity':False}
    return {'cms_document_identity':True,**section_checks(spec,state.get('sections'),
        issued_request=issued_request,current_url=state['url'])}


FEEDBACK={'cms_document_identity':'The displayed document is the requested native CMS page.'}
