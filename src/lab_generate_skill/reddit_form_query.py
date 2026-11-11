"""Queries about pinned native form documentation, with private literal references.

References are captured from two independent native deployments. They are never
put into actor input. Live controls must independently read the public form/help
and match the reference; opening help alone is not a correct query answer.
"""
import re
from pathlib import Path
from urllib.parse import urlsplit
from .query_record_sets import canonical_records


def normalize(value):
    if not isinstance(value,str):raise ValueError('Expected native form text')
    return ' '.join(value.split())


def validate(q):
    if q.get('family')!='reddit_form_documentation' or q.get('form_kind') not in ('submission','wiki'):
        raise ValueError('Unsupported native form documentation')
    kind=q.get('query_kind')
    if kind not in ('formatting','required_fields') or kind=='required_fields' and q['form_kind']!='wiki':
        raise ValueError('Unsupported native form query')
    shape={'feature':'string','syntax':'string'} if kind=='formatting' else {'name':'string'}
    if q.get('fields')!={'items':'record_set'} or q.get('record_fields')!={'items':shape}:
        raise ValueError('Unexpected native form answer schema')
    canonical_records(q['reference_values']['items'],shape)
    if not q['reference_values']['items']:raise ValueError('Empty native form reference')


def reference(site,q):
    validate(q)
    # This is a literal task reference like a static benchmark answer. Reject
    # image replacement before trusting documentation captured from that image.
    p=Path(site.root)/'containers/webarena/reddit.sif';s=p.stat()
    if {'bytes':s.st_size,'mtime_ns':s.st_mtime_ns}!=q['image_metadata']:
        raise ValueError('Native form image changed; fresh controls required')
    return {'object_id':q['family']+':'+q['form_kind']+':'+q['query_kind'],'values':q['reference_values'],
            'source_image_metadata':q['image_metadata']}


def required_fields(page):
    rows=page.locator('form input,form textarea,form select').evaluate_all('''es=>es.filter(e=>
      e.name.startsWith('wiki[') && e.required && e.type!=='hidden' && !!e.getClientRects().length)
      .map(e=>({name:e.name,labels:[...(e.labels||[])].map(l=>l.innerText)}))''')
    result=[]
    for r in rows:
        labels=[normalize(s).removesuffix('*').strip() for s in r['labels'] if '*' in s]
        if len(labels)!=1:raise ValueError('Required field label absent or ambiguous')
        result.append({'name':labels[0]})
    if not result or len(result)!=len({r['name'] for r in result}):raise ValueError('Required fields missing or duplicated')
    return result


def ui_values(page,q):
    validate(q);path=urlsplit(page.url).path
    if q['form_kind']=='submission' and path!='/submit' or q['form_kind']=='wiki' and not re.fullmatch(r'/wiki/_create(?:/[^?]*)?',path):
        raise ValueError('Wrong native form page')
    if q['query_kind']=='required_fields':return {'items':required_fields(page)}
    ident={'submission':'submission_body_markdown_help','wiki':'wiki_body_markdown_help'}[q['form_kind']]
    checkbox=page.locator('#'+ident)
    if checkbox.count()!=1:raise ValueError('Native formatting help missing')
    # CPU reference-observability check only; never invoked by an actor tool.
    if not checkbox.is_checked():page.locator('label[for="'+ident+'"]').click(timeout=10000)
    table=checkbox.locator('..').locator('table.formatting-help')
    if table.count()!=1 or not table.is_visible():raise ValueError('Native formatting table not visible')
    rows=table.locator('tr').evaluate_all('rs=>rs.map(r=>[...r.querySelectorAll("td")].map(c=>c.innerText))')
    if not rows or any(len(r)!=2 for r in rows):raise ValueError('Malformed native formatting table')
    return {'items':[{'feature':normalize(r[0]),'syntax':normalize(r[1])} for r in rows]}
