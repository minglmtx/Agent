"""Private Git/SQL references and independent native UI metadata readers.

Only the public field meaning enters the actor prompt. Reference commit IDs,
license text, storage bytes and control navigation stay outside actor input.
"""
import hashlib
import re
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import unquote, urlsplit

from .site_database import select_rows


def storage_label(size):
    """GitLab StorageHelper#storage_counter (binary units, fixed precision)."""
    if type(size) is not int or size < 0:
        raise ValueError('Invalid project storage size')
    units = ('Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB')
    unit = 0
    while size >= 1024 ** (unit + 1) and unit < len(units) - 1:
        unit += 1
    precision = 0 if size < 1024 ** 2 else 1
    value = (Decimal(size) / Decimal(1024 ** unit)).quantize(
        Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP)
    text = format(value, ',f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text + ' ' + ('Byte' if size == 1 else units[unit])


def license_label(text):
    """Recognize supported complete native license forms; fail on unknown text."""
    text = ' '.join(text.split()).casefold()
    mit = all(x in text for x in (
        'permission is hereby granted, free of charge',
        'the above copyright notice and this permission notice shall be included',
        'the software is provided "as is"',
        'including but not limited to the warranties of merchantability',
    ))
    apache = all(x in text for x in (
        'apache license version 2.0, january 2004',
        'terms and conditions for use, reproduction, and distribution',
        'grant of copyright license', 'grant of patent license',
        'end of terms and conditions',
    ))
    if mit == apache:
        raise ValueError('Unsupported or ambiguous license document')
    return 'MIT License' if mit else 'Apache License 2.0'


def normalized_text(text):
    return ' '.join(text.split())


def declared_language(text, subject):
    """Read an explicit subject-bound implementation-language declaration.

    This does not infer a language from code snippets, filenames, related
    projects or keyword frequency. Unsupported/ambiguous prose stays unknown.
    """
    if not isinstance(subject,str)or not re.fullmatch(r'[A-Za-z0-9_.-]+',subject):
        raise ValueError('Explicit repository subject required')
    text=re.sub(r'\[([^\]\n]+)\]\([^\)\n]+\)',r'\1',text).replace('`','')
    languages=('Go','Python','JavaScript','TypeScript','Rust','Java','Ruby','C++','C#','C')
    pattern=(r'^'+re.escape(subject)+r'\s+is\s+[^\n]{0,200}?\b(?:implementation|library|client|tool)\s+'
             r'(?:written\s+)?in\s+('+'|'.join(map(re.escape,languages))+r')(\s+\(golang\))?\.?\s*$')
    matches=re.findall(pattern,text,re.MULTILINE)
    if len({language for language,alias in matches})!=1 or any(alias and language!='Go'for language,alias in matches):
        raise ValueError('Missing or conflicting explicit language declaration')
    return matches[0][0]


def blob_text_without_line_numbers(text):
    """Vue blob viewer interleaves native line-number nodes and file lines."""
    lines=text.splitlines()
    numbers=[int(s.strip()) for s in lines if re.fullmatch(r'\d+',s.strip())]
    if numbers:
        if len(numbers)<3 or numbers!=list(range(1,len(numbers)+1)) or lines[0].strip()!='1':
            raise ValueError('Ambiguous numbered license rendering')
        lines=[s for s in lines if not re.fullmatch(r'\d+',s.strip())]
    return '\n'.join(lines)


def rendered_commit_message(title, description):
    """Commit#description contains the FULL message when first line >=100 chars.

    For short titles it contains only the body. Source: native app/models/commit.rb.
    The independent Git reference comparison remains mandatory at admission.
    """
    first=description.splitlines()[0] if description else ''
    if len(first)>=100 and title.endswith('...') and first.startswith(title[:-3]):
        return normalized_text(description)
    return normalized_text(title+'\n'+description)


def reference(site, query):
    ident = query['object_id']
    if type(ident) is not int or ident <= 0:
        raise ValueError('Invalid project identity')
    rows = select_rows(site, f"SELECT p.id,r.path FROM projects p JOIN routes r ON r.source_id=p.id AND r.source_type='Project' WHERE p.id={ident}")
    if len(rows) != 1 or rows[0]['path'] != query['project']:
        raise ValueError('Project route/reference mismatch')
    digest = hashlib.sha256(str(ident).encode()).hexdigest()
    repo = '/var/opt/gitlab/git-data/repositories/@hashed/' + digest[:2] + '/' + digest[2:4] + '/' + digest + '.git'

    def git(*args):
        r = site.command(['/opt/gitlab/embedded/bin/git', '--git-dir=' + repo, *args],
                         capture_output=True, text=True, timeout=40)
        if r.returncode:
            raise RuntimeError('Private Git metadata read failed')
        return r.stdout.rstrip('\n')

    head = git('rev-parse', 'HEAD')
    if not re.fullmatch(r'[0-9a-f]{40}', head) or head != query['head']:
        raise ValueError('Repository HEAD differs from pinned snapshot')
    values = {}
    evidence = {'head': head}
    for key in query['fields']:
        if key == 'storage_size':
            rows = select_rows(site, f'SELECT storage_size FROM project_statistics WHERE project_id={ident}')
            if len(rows) != 1:
                raise ValueError('Missing project storage reference')
            evidence['storage_bytes'] = int(rows[0]['storage_size'])
            values[key] = storage_label(evidence['storage_bytes'])
        elif key == 'latest_commit_message':
            values[key] = normalized_text(git('log', '-1', '--format=%B', 'HEAD'))
            if not values[key]:
                raise ValueError('Empty commit message')
        elif key == 'file_updated_date':
            from .gitlab_project_date_query import utc_date
            path=query.get('file_path','');ref=query.get('file_ref','')
            if (not path or path.startswith('/') or any(x in ('','.','..')for x in path.split('/'))
                    or not re.fullmatch(r'[A-Za-z0-9_.][A-Za-z0-9_./-]*',ref) or '..'in ref
                    or query.get('reference_path')!='/'+query['project']+'/-/blob/'+ref+'/'+path):
                raise ValueError('Explicit pinned file page required')
            if git('rev-parse','refs/heads/'+ref)!=head:raise ValueError('File branch differs from pinned HEAD')
            # The blob header shows the author date of the latest affecting
            # commit. Do not substitute project.updated_at or HEAD's date.
            if git('cat-file','-t',head+':'+path)!='blob':raise ValueError('Requested object is not a file')
            lines=git('log','-1','--format=%H%n%aI',head,'--',path).splitlines()
            if len(lines)!=2 or not re.fullmatch('[0-9a-f]{40}',lines[0]):raise ValueError('File commit metadata missing')
            values[key]=utc_date(lines[1]);evidence['file_commit']=lines[0];evidence['file_author_timestamp']=lines[1]
        elif key == 'license_type':
            path = query['license_path']
            if path.startswith('/') or any(x in ('', '.', '..') for x in path.split('/')):
                raise ValueError('Invalid license path')
            text = git('show', 'HEAD:' + path)
            values[key] = license_label(text)
            evidence['license_sha256'] = hashlib.sha256(normalized_text(text).encode()).hexdigest()
        elif key == 'declared_language':
            path=query.get('declaration_path','')
            if (not path or path.startswith('/')or any(x in ('','.','..')for x in path.split('/'))
                or query.get('declaration_subject')!=query['project'].split('/')[-1]
                or query.get('reference_path')!='/'+query['project']):
                raise ValueError('Pinned repository declaration identity required')
            if git('cat-file','-t',head+':'+path)!='blob':raise ValueError('Declaration document missing')
            text=git('show',head+':'+path)
            values[key]=declared_language(text,query['declaration_subject'])
            evidence['declaration_sha256']=hashlib.sha256(text.encode()).hexdigest()
        else:
            raise ValueError('Unsupported repository metadata field')
    return {'object_id': 'gitlab_project:' + str(ident), 'values': values, 'evidence': evidence}


def ui_values(page, query):
    ids = page.locator('[data-project-id]').evaluate_all(
        'es=>[...new Set(es.map(e=>e.getAttribute("data-project-id")))]')
    if not ids or any(x != str(query['object_id']) for x in ids):
        raise ValueError('Rendered project identity mismatch')
    if unquote(urlsplit(page.url).path).rstrip('/') != query['reference_path'].rstrip('/'):
        raise ValueError('Unexpected metadata reference page')
    values = {}
    for key in query['fields']:
        if key == 'storage_size':
            body = page.locator('body').inner_text()
            matches = re.findall(r'([\d,.]+\s+(?:Bytes?|KB|MB|GB|TB|PB|EB))\s+Project Storage', body)
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous displayed storage size')
            values[key] = normalized_text(matches[0])
        elif key == 'latest_commit_message':
            title = page.locator('.commit-box .commit-title')
            title.wait_for(state='visible', timeout=10000)
            if title.count() != 1:
                raise ValueError('Ambiguous commit message title')
            title_text=title.inner_text().strip()
            desc = page.locator('.commit-box .commit-description')
            if desc.count() > 1:
                raise ValueError('Ambiguous commit message body')
            values[key] = rendered_commit_message(title_text,desc.inner_text() if desc.count() else '')
        elif key == 'file_updated_date':
            from .gitlab_project_date_query import utc_date
            from .gitlab_repository import read_repository_page
            state=read_repository_page(page)
            if state['wait_status']!='ready' or not state['content']:raise ValueError('Native file content not loaded')
            times=page.locator('time').evaluate_all('''es=>es.filter(e=>e.getClientRects().length).map(e=>({
              timestamp:e.getAttribute('datetime'),context:e.parentElement.innerText}))''')
            times=[t for t in times if re.search(r'\bauthored\b',t['context'])]
            if len(times)!=1:raise ValueError('Native file author timestamp absent or ambiguous')
            values[key]=utc_date(times[0]['timestamp'])
        elif key == 'license_type':
            content = page.locator('.file-content.blob-content')
            content.wait_for(state='visible', timeout=10000)
            if content.count() != 1:
                raise ValueError('Missing or ambiguous native license text')
            values[key] = license_label(blob_text_without_line_numbers(content.inner_text()))
        elif key == 'declared_language':
            from .gitlab_repository import read_repository_page
            state=read_repository_page(page)
            if state.get('wait_status')!='ready'or len(state.get('content',[]))!=1:
                raise ValueError('Native declaration document not loaded or ambiguous')
            values[key]=declared_language(state['content'][0],query['declaration_subject'])
        else:
            raise ValueError('Unsupported metadata UI field')
    return values
