"""Deterministic full native Markdown prose equivalence for private evaluation.

Source text comes from an independently pinned Git object, never from an actor
answer. Public content must be a complete native rendered Markdown block; a raw
SHA mismatch alone is expected because GitLab removes Markdown punctuation.
This verifies prose, code and reference attributes, not image pixels, reading
comprehension or equivalence to a model judge. It does not wait or navigate.
"""
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from markdown_it import MarkdownIt


def normalized(text):
    return ' '.join(text.split())


def frontmatter_parts(source):
    source=source.replace('\r\n','\n')
    if not source.startswith('---\n'):
        return None,source
    match=re.fullmatch(r'---\n(.*?)\n---\n(.*)',source,re.S)
    if not match:raise ValueError('Unclosed Markdown frontmatter')
    return match[1],match[2]


def native_path(value,project,ref):
    # GitLab's native renderer interprets a root-relative Markdown image as a
    # repository-root blob path. Absolute external links are not rewritten.
    if value.startswith('/')and not value.startswith('//'):
        return '/'+project+'/-/blob/'+ref+value
    return value


def rendered_markdown_checks(source,native_html,*,project,ref,capture_truncated):
    checks={'complete_native_capture':capture_truncated is False,
            'native_markdown_block':False,'frontmatter_complete':False,
            'full_rendered_prose_equivalent':False,
            'inline_reference_attributes_equivalent':False,
            'image_elements_equivalent':False}
    if not checks['complete_native_capture']or not isinstance(source,str)or not isinstance(native_html,str):return checks
    root=BeautifulSoup(native_html,'html.parser')
    blocks=root.select('.file-content.md')
    if len(blocks)!=1:return checks
    native=blocks[0];checks['native_markdown_block']=True
    metadata,body=frontmatter_parts(source)
    if metadata is not None:
        first=next((node for node in native.children if getattr(node,'name',None)),None)
        if not first or 'markdown-code-block'not in first.get('class',[]):return checks
        code=first.select_one('code')
        if code is None or normalized(code.get_text())!=normalized(metadata):return checks
        first.decompose()
    checks['frontmatter_complete']=True
    for item in native.select('button,svg,script,style,.anchor,[hidden],[aria-hidden="true"],.gl-display-none'):
        item.decompose()
    for item in list(native.select('[style]')):
        if re.search(r'(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))\b',item.get('style',''),re.I):item.decompose()
    expected=BeautifulSoup(MarkdownIt('commonmark').render(body),'html.parser')
    checks['full_rendered_prose_equivalent']=normalized(expected.get_text(' ',strip=True))==normalized(native.get_text(' ',strip=True))
    expected_images=[(native_path(image.get('src',''),project,ref),image.get('alt',''))for image in expected.select('img')]
    actual_images=[(image.get('src',''),image.get('alt',''))for image in native.select('img')]
    checks['image_elements_equivalent']=expected_images==actual_images
    # The native renderer adds a link around Markdown images. Ignore only
    # that exact wrapper; a missing/changed ordinary reference is still false.
    for link in list(native.select('a[href]')):
        if not link.get_text(strip=True)and len(link.select('img'))==1 and link['href']==link.select_one('img').get('src'):
            link.unwrap()
    expected_links=[(normalized(link.get_text(' ',strip=True)),link.get('href'))for link in expected.select('a[href]')]
    actual_links=[(normalized(link.get_text(' ',strip=True)),link.get('href'))for link in native.select('a[href]')]
    checks['inline_reference_attributes_equivalent']=expected_links==actual_links
    return checks
