"""Pure native formatting-help observation, without opening a panel for actor.

Private controls may open the native checkbox/label. This reader and checker
never do so, and a help heading alone cannot replace the required native rows.
References are independently captured native documentation, not task answers
inserted into the public page or actor input.
"""
import re
from urllib.parse import urlsplit

VERSION = 'reddit-native-formatting-navigation-draft-v1'

READ = r'''() => {
 const visible=e=>{if(!e||!e.isConnected||![...e.getClientRects()].some(r=>r.width>0&&r.height>0))return false;for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||Number(s.opacity)===0)return false;if(n.tagName==='DETAILS'&&!n.open&&!n.querySelector(':scope > summary')?.contains(e))return false;}return true;};
 return {version:'reddit-native-formatting-navigation-draft-v1',url:location.href,
  tables:[...document.querySelectorAll('table.formatting-help')].map(table=>{
   const owner=table.parentElement;
   const boxes=owner?[...owner.querySelectorAll(':scope > input.hideable__checkbox[type=checkbox]')]:[];
   const checkbox=boxes.length===1?boxes[0]:null;
   const textarea=checkbox?.id?.replace(/_markdown_help$/,'');
   const field=textarea?document.getElementById(textarea):null;
   return {checkbox_id:checkbox?.id||null,checked:checkbox?.checked??null,visible:visible(table),
    native_body_field:field?.tagName==='TEXTAREA'?{id:field.id,name:field.name,visible:visible(field)}:null,
    rows:[...table.querySelectorAll(':scope > tbody > tr')].map(row=>({visible:visible(row),
     cells:[...row.querySelectorAll(':scope > td')].map(cell=>({text:cell.innerText,visible:visible(cell)}))}))};
  })};
}'''


def _text(value):
    if not isinstance(value, str):
        raise ValueError('Exact native documentation text must be a string')
    return ' '.join(value.split())


def _origin(value):
    u = urlsplit(value)
    if (u.scheme not in ('http', 'https') or not u.hostname or u.username is not None
            or u.password is not None or u.path not in ('', '/') or u.query or u.fragment):
        raise ValueError('Trusted actual local factory origin required')
    u.port
    return u.scheme, u.netloc


def validate(spec):
    if (not isinstance(spec, dict) or set(spec) != {'form_kind', 'required_rows'}
            or spec['form_kind'] not in ('wiki', 'submission', 'comment')
            or not isinstance(spec['required_rows'], list) or not spec['required_rows']):
        raise ValueError('Complete native form documentation scope required')
    rows = []
    for row in spec['required_rows']:
        if not isinstance(row, dict) or set(row) != {'feature', 'syntax'}:
            raise ValueError('Complete independent native documentation row required')
        value = (_text(row['feature']), _text(row['syntax']))
        if not all(value):
            raise ValueError('Empty native documentation row')
        rows.append(value)
    if len(set(rows)) != len(rows):
        raise ValueError('Duplicate independent native documentation row')
    return rows


def _valid_path(path, kind):
    if kind == 'submission':
        return path == '/submit'
    if kind == 'wiki':
        return bool(re.fullmatch(r'/wiki/(?:_create|_edit)(?:/[^/]+(?:/[^/]+)*)?', path))
    return bool(re.fullmatch(r'/f/[^/]+/[1-9][0-9]*(?:/[^/]+)?', path))


def native_body_field_matches(kind,field,ident,public_url):
    """Match installed Symfony form names, including native dynamic replies."""
    if (not isinstance(field,dict) or field.get('visible') is not True or not isinstance(ident,str)
        or not isinstance(field.get('id'),str) or not isinstance(field.get('name'),str)
        or ident!=field['id']+'_markdown_help'):
        return False
    if kind!='comment':return field['name']==kind+'[body]'
    name=re.fullmatch(r'(reply_to_(submission|comment)_([1-9][0-9]*))\[comment\]',field['name'])
    if name is None:return False
    if field['id']!=name[1]+'_comment':return False
    if name[2]=='submission':
        path=re.fullmatch(r'/f/[^/]+/([1-9][0-9]*)(?:/[^/]+)?',urlsplit(public_url).path)
        if path is None or path[1]!=name[3]:return False
    return True


def checks(spec, public, *, site_origin):
    required = set(validate(spec))
    if (not isinstance(public, dict) or public.get('version') != VERSION
            or not isinstance(public.get('tables'), list)
            or type(public.get('http_status')) is not int
            or type(public.get('login_page')) is not bool
            or type(public.get('error_page')) is not bool):
        raise ValueError('Complete native terminal documentation capture required')
    u = urlsplit(public['url'])
    local = (u.scheme, u.netloc) == _origin(site_origin) and u.username is None and u.password is None
    path_matches = local and not u.query and not u.fragment and _valid_path(u.path, spec['form_kind'])
    matching = []
    for table in public['tables']:
        if (not isinstance(table, dict) or set(table) != {'checkbox_id', 'checked', 'visible', 'native_body_field', 'rows'}
                or type(table['visible']) is not bool or not isinstance(table['rows'], list)):
            raise ValueError('Complete native formatting table capture required')
        ident = table['checkbox_id']
        checked = table['checked']
        field = table['native_body_field']
        if ident is not None and not isinstance(ident, str) or checked is not None and type(checked) is not bool:
            raise ValueError('Malformed native checkbox state')
        if field is not None and (not isinstance(field, dict) or set(field) != {'id', 'name', 'visible'}
                or type(field['visible']) is not bool or not isinstance(field['id'], str) or not isinstance(field['name'], str)):
            raise ValueError('Complete public native body field identity required')
        rows = []
        for row in table['rows']:
            if (not isinstance(row, dict) or set(row) != {'visible', 'cells'}
                    or type(row['visible']) is not bool or not isinstance(row['cells'], list)):
                raise ValueError('Complete native documentation row capture required')
            cells = []
            for cell in row['cells']:
                if (not isinstance(cell, dict) or set(cell) != {'text', 'visible'}
                        or type(cell['visible']) is not bool):
                    raise ValueError('Complete native documentation cell capture required')
                cells.append(_text(cell['text']))
            if len(cells) == 2 and row['visible'] and all(cell['visible'] for cell in row['cells']):
                rows.append(tuple(cells))
        canonical = set(rows)
        scoped_field = native_body_field_matches(spec['form_kind'],field,ident,public['url'])
        if scoped_field:
            matching.append({'open': checked is True and table['visible'],
                             'complete': required <= canonical and len(rows) == len(canonical)})
    return {
        'native_documentation_correct_local_form': bool(path_matches),
        'native_documentation_unique_body_help': len(matching) == 1,
        'native_documentation_panel_open_and_visible': len(matching) == 1 and matching[0]['open'],
        'native_documentation_required_rows_visible': len(matching) == 1 and matching[0]['complete'],
        'native_documentation_valid_terminal_document': 200 <= public['http_status'] < 300
                                                      and not public['login_page'] and not public['error_page'],
    }


def read(page):
    """Observation only: no checkbox operation, navigation or reference injection."""
    return page.evaluate(READ)
