"""Local browser network policy preserving Chromium-owned multipart bytes.

Some pinned Playwright Python versions initialize the fallback override body from
CDP's postData, which omits uploaded file bytes. Serializing it in continue_()
turns an otherwise untouched multipart upload into PHP UPLOAD_ERR_PARTIAL.
Only discard that *unchanged diagnostic copy*, never an explicit body override.
The browser then sends its original upload, including the actual file bytes.
"""
import base64
from urllib.parse import urlsplit


def continue_unchanged(route):
    request = route.request
    if 'multipart/form-data' in request.headers.get('content-type', '').lower():
        impl = request._impl_obj
        overrides = impl._fallback_overrides
        data = overrides.post_data_buffer
        original = impl._initializer.get('postData')
        if data is not None:
            if original is None or data != base64.b64decode(original):
                raise RuntimeError('Refuse to discard an explicitly modified multipart body')
            overrides.post_data_buffer = None
    route.continue_()


def install_local_network_policy(context, local_netloc):
    # A multi-service site declares exact leased authorities; never allow every
    # localhost port, which could expose another worker's private environment.
    allowed = frozenset([local_netloc] if isinstance(local_netloc, str) else local_netloc)
    if not allowed or any(not isinstance(value, str) or not value or "/" in value for value in allowed):
        raise ValueError("Explicit local service authorities required")
    context._lab_navigation_blocks = {}
    context._lab_blocked_documents = {}
    def local_only(route):
        request = route.request
        navigation = callable(getattr(request, 'is_navigation_request', None)) and request.is_navigation_request()
        page = request.frame.page if navigation else None
        top_level = navigation and request.frame == page.main_frame
        if top_level:
            context._lab_blocked_documents.pop(page, None)
            if not getattr(page, '_lab_block_document_listener', False) and callable(getattr(page, 'on', None)):
                def document_changed(frame):
                    if frame == page.main_frame and page.url != 'chrome-error://chromewebdata/':
                        context._lab_blocked_documents.pop(page, None)
                page.on('framenavigated', document_changed)
                page._lab_block_document_listener = True
        url = urlsplit(route.request.url)
        if url.scheme in ('data', 'blob', 'about') or (url.scheme in ('http', 'https') and url.netloc in allowed):
            continue_unchanged(route)
        else:
            request=route.request
            if callable(getattr(request,'is_navigation_request',None)) and request.is_navigation_request():
                page=request.frame.page
                if request.frame==page.main_frame:
                    # Only the current top-level navigation, not blocked ads,
                    # images or embedded frames. Never store query credentials.
                    host=url.hostname or ''
                    if ':' in host:host='['+host+']'
                    origin=url.scheme+'://'+host+((':'+str(url.port)) if url.port else '')
                    context._lab_navigation_blocks[page]={'blocked_origin':origin,
                        'reason':'outside_declared_local_services','source':'local_network_policy'}
                    context._lab_blocked_documents[page] = dict(context._lab_navigation_blocks[page])
            route.abort()
    context.route('**/*', local_only)


def consume_navigation_block(page):
    """A single action's public execution feedback, without goal/evaluator input."""
    return getattr(page.context,'_lab_navigation_blocks',{}).pop(page,None)


def blocked_terminal_document(page):
    """Retain policy evidence after public action feedback is consumed.

    Only the current browser error document qualifies. A later navigation or
    another tab must not inherit this classification. No HTTP status is made up.
    """
    if page.url != 'chrome-error://chromewebdata/':
        return None
    evidence = getattr(page.context, '_lab_blocked_documents', {}).get(page)
    return dict(evidence, document_url=page.url) if evidence else None
