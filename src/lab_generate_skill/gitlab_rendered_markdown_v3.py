"""Complete native Markdown content checks compatible with actual GitLab DOM.

Private evaluation only, no waiting/navigation/model calls. Compared with v2,
inline syntax-highlighting spans do not manufacture source whitespace, native
relative image URLs use raw-file routes, and only demonstrably literal HTTP(S)
URL autolinks are accepted in addition to the source's explicit references.
Native lazy-image data-src is a reference, not a decoded image.
These content checks do not validate comprehension or decoded image pixels.
"""
import re
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from markdown_it import MarkdownIt
from .gitlab_rendered_markdown_v2 import frontmatter_parts, native_path, normalized

BLOCKS = {'address', 'article', 'aside', 'blockquote', 'dd', 'div', 'dl', 'dt',
          'figcaption', 'figure', 'footer', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
          'header', 'hr', 'li', 'main', 'nav', 'ol', 'p', 'pre', 'section',
          'table', 'tbody', 'td', 'th', 'thead', 'tr', 'ul'}


def rendered_prose(node):
    """Preserve literal inline/code text, separating only rendered blocks.

BeautifulSoup.get_text(' ', strip=True) inserts spaces at every Prism span,
so e.g. src=\"x\" becomes src= \"x\" although no source character is missing.
Inline elements add no invented separator; block boundaries and BR do.
"""
    def collect(item):
        if isinstance(item, Comment):
            return ''
        if isinstance(item, NavigableString):
            return str(item)
        if not isinstance(item, Tag):
            return ''
        if item.name == 'br':
            return ' '
        value = ''.join(collect(child) for child in item.children)
        return ' ' + value + ' ' if item.name in BLOCKS else value
    return normalized(collect(node))


def image_path(value, project, ref, path):
    # Actual pinned GitLab: relative image files resolve to /-/raw/, while
    # root-relative A11Y images retain the native /-/blob/ interpretation.
    if not value.startswith(('/', '#')) and not urlsplit(value).scheme:
        parent = path.rsplit('/', 1)[0] + '/' if '/' in path else ''
        return urljoin('/' + project + '/-/raw/' + ref + '/' + parent, value)
    return native_path(value, project, ref, path)


NATIVE_LAZY_PLACEHOLDER = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=='


def native_image_reference(image):
    """Read native reference before or after GitLab lazy-image hydration.

    Accept data-src only for the exact real GitLab placeholder and lazy
    class. Never override a real or arbitrary broken src with data-src, and
    never claim the advertised reference has fetched or decoded its pixels.
    """
    current = image.get('src', '')
    advertised = image.get('data-src')
    if (current == NATIVE_LAZY_PLACEHOLDER and 'lazy' in image.get('class', [])
            and isinstance(advertised, str) and advertised):
        return advertised
    return current


def native_image_diagnostics(native_html):
    root = BeautifulSoup(native_html, 'html.parser')
    images = root.select('.file-content.md img')
    unresolved = sum(native_image_reference(image) != image.get('src', '') for image in images)
    return {'native_image_elements': len(images),
            'native_lazy_references_not_materialized': unresolved,
            'reference_equivalence_does_not_verify_image_pixels': True}


def literal_urls(expected):
    """Public literal URLs outside explicit links/code, from source rendering."""
    found = set()
    for node in expected.find_all(string=True):
        if isinstance(node, Comment) or node.find_parent(['a', 'code', 'pre', 'script', 'style']):
            continue
        for url in re.findall(r'https?://[^\s<>\"\'`]+', str(node)):
            url = url.rstrip('.,;:!?')
            for close, opening in [(')', '('), (']', '['), ('}', '{')]:
                while url.endswith(close) and url.count(close) > url.count(opening):
                    url = url[:-1]
            found.add(url)
    return found


def reference_links_equivalent(expected, native, project, ref, path):
    wanted = [(rendered_prose(link), native_path(link.get('href', ''), project, ref, path))
              for link in expected.select('a[href]')]
    literal = literal_urls(expected)
    index = 0
    for link in native.select('a[href]'):
        observed = (rendered_prose(link), link.get('href'))
        if index < len(wanted) and observed == wanted[index]:
            index += 1
        elif observed[0] == observed[1] and observed[1] in literal:
            # GitLab automatically links source text URLs. Do not accept a
            # changed target, arbitrary label, or a newly invented reference.
            continue
        else:
            return False
    return index == len(wanted)


def rendered_markdown_checks(source, native_html, *, project, ref, path, capture_truncated):
    checks = {'complete_native_capture': capture_truncated is False,
              'native_markdown_block': False, 'frontmatter_complete': False,
              'full_rendered_prose_equivalent': False,
              'inline_reference_attributes_equivalent': False,
              'image_elements_equivalent': False}
    if not checks['complete_native_capture'] or not isinstance(source, str) or not isinstance(native_html, str):
        return checks
    root = BeautifulSoup(native_html, 'html.parser')
    blocks = root.select('.file-content.md')
    if len(blocks) != 1:
        return checks
    native = blocks[0]
    checks['native_markdown_block'] = True
    metadata, body = frontmatter_parts(source)
    if metadata is not None:
        first = next((node for node in native.children if getattr(node, 'name', None)), None)
        if not first or 'markdown-code-block' not in first.get('class', []):
            return checks
        code = first.select_one('code')
        if code is None or normalized(code.get_text()) != normalized(metadata):
            return checks
        first.decompose()
    checks['frontmatter_complete'] = True
    for item in native.select('button,svg,script,style,.anchor,[hidden],[aria-hidden="true"],.gl-display-none'):
        item.decompose()
    for item in list(native.select('[style]')):
        if re.search(r'(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))\b', item.get('style', ''), re.I):
            item.decompose()
    expected = BeautifulSoup(MarkdownIt('commonmark').render(body), 'html.parser')
    checks['full_rendered_prose_equivalent'] = rendered_prose(expected) == rendered_prose(native)
    expected_images = [(image_path(image.get('src', ''), project, ref, path), image.get('alt', ''))
                       for image in expected.select('img')]
    actual_images = [(native_image_reference(image), image.get('alt', '')) for image in native.select('img')]
    checks['image_elements_equivalent'] = expected_images == actual_images
    for link in list(native.select('a[href]')):
        if not link.get_text(strip=True) and len(link.select('img')) == 1 and link['href'] == native_image_reference(link.select_one('img')):
            link.unwrap()
    checks['inline_reference_attributes_equivalent'] = reference_links_equivalent(expected, native, project, ref, path)
    return checks
