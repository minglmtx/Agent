"""Explicit local browser printing; no task answer, navigation, or success rule.

This capability is opt-in until its site-specific artifact checks are admitted.
The actual current document is printed with Chromium's print stylesheet. It is
not a screenshot, a synthesized route, or a server download. Receipts remain
separate from DownloadRecorder so neither provenance can impersonate the other.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from .io_utils import atomic_write_json
from .runtime_watchdog import deadline_scope

MAX_BYTES = 32 * 1024 * 1024
MAX_PAGES = 64
OPTIONS = dict(format='A4', print_background=True, display_header_footer=False,
               prefer_css_page_size=False,
               margin=dict(top='10mm', bottom='10mm', left='10mm', right='10mm'))


def pdf_text(body):
    """Read all pages, including long directions; never silently truncate."""
    import pymupdf
    if not isinstance(body, bytes) or not body.startswith(b'%PDF-') or len(body) > MAX_BYTES:
        raise ValueError('Bounded actual print PDF required')
    try:
        with pymupdf.open(stream=body, filetype='pdf') as doc:
            if (doc.is_encrypted or doc.is_repaired or doc.embfile_count()
                    or not 1 <= doc.page_count <= MAX_PAGES):
                raise ValueError('Intact bounded print document required')
            pages = []
            for page in doc:
                if not 0 < page.rect.width <= 2000 or not 0 < page.rect.height <= 2000:
                    raise ValueError('Unbounded print page')
                pages.append(page.get_text('text'))
            return pages
    except (RuntimeError, pymupdf.FileDataError) as error:
        raise ValueError('Unreadable print PDF') from error


def document_state(page):
    if urlsplit(page.url).scheme not in ('http', 'https'):
        raise ValueError('A real website document is required for printing')
    value = page.evaluate('''() => ({url:location.href, title:document.title,
        text:document.body ? document.body.innerText : null})''')
    if not isinstance(value.get('text'), str) or len(value['text']) > 1_000_000:
        raise ValueError('Bounded printable document unavailable')
    return value


class PrintRecorder:
    def __init__(self, directory, *, source_reader=None, print_layout=None):
        # Fail before inference if the enabled environment lacks its PDF reader.
        import pymupdf  # noqa: F401
        from .map_route_print_layout import VERSION
        if print_layout not in (None, VERSION):
            raise ValueError('Unknown trusted print layout')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.records = []
        self.source_reader = source_reader
        self.print_layout = print_layout

    def source(self, page):
        value = document_state(page)
        if self.source_reader is not None:
            # Read-only runtime evidence. Never supplied by the actor or embedded in its PDF.
            value['native'] = self.source_reader(page)
        return value

    def save(self):
        atomic_write_json(self.directory / 'prints.json', dict(
            version='browser-print-to-pdf-v1', prints=self.records,
            task_success_inferred=False, automatic_navigation=False))

    def print_page(self, page):
        number = len(self.records) + 1
        row = dict(print_id=number, filename=f'print-{number:04d}.pdf', status='pending')
        self.records.append(row)
        self.save()
        try:
            with deadline_scope('browser_print_to_pdf', 60):
                before = self.source(page)
                # Record source before entering the renderer, for interrupted attempts.
                atomic_write_json(self.directory / f'source-{number:04d}.json', before)
                style = None
                try:
                    if self.print_layout is not None:
                        from .map_route_print_layout import install
                        style, metadata = install(page)
                        row['print_layout'] = metadata
                        self.save()
                    body = page.pdf(**OPTIONS)
                finally:
                    if style is not None:
                        style.evaluate('(element) => element.remove()')
                after = self.source(page)
                (self.directory / row['filename']).write_bytes(body)
                row.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                pages = pdf_text(body)
                if before != after:
                    raise ValueError('Document changed while printing; captured artifact is unverified')
                row.update(status='completed', page_count=len(pages),
                           source_url=before['url'],
                           source_sha256=hashlib.sha256(json.dumps(before, sort_keys=True,
                               ensure_ascii=False).encode()).hexdigest(),
                           renderer='chromium-page-pdf', options=OPTIONS)
        except Exception as error:
            row.update(status='failed', error_type=type(error).__name__)
            self.save()
            raise
        self.save()
        return dict(row)

    def observation(self, obs):
        # Public artifact facts only; no evaluator or private reference fields.
        rows = [{k: v for k, v in r.items() if k in
                 ('print_id', 'filename', 'status', 'bytes', 'page_count', 'sha256')}
                for r in self.records]
        return {**obs, 'browser_capabilities': {
            **obs.get('browser_capabilities', {}), 'print_to_pdf': True},
            'printed_files': rows,
            'print_feedback': 'print_page() saves the current page using browser print layout '
                'as a local PDF. A completed print file does not establish task success.'}
