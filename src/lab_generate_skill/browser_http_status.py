"""Read browser HTTP evidence without reloading a document or assuming success."""


def watch_document_responses(context):
    """Bind listeners only after a Page exists; pair with terminal native timing."""
    responses={}
    def attach(page):
        def observe(response):
            if response.request.is_navigation_request()and response.frame==page.main_frame:
                responses[page]={'url':response.url,'http_status':response.status}
        page.on('response',observe)
    context.on('page',attach)
    for page in context.pages:attach(page)
    return responses


def native_document_status(page, response):
    if response is not None:
        return response.status
    # Fragment and same-document navigation have no new response. The current
    # document's navigation timing retains its native HTTP status, including
    # 404/500. Zero/unavailable must stay unknown.
    status = page.evaluate('() => performance.getEntriesByType("navigation")[0]?.responseStatus ?? null')
    return status if type(status) is int and 100 <= status <= 599 else None


def terminal_document_evidence(page, observed=None):
    """Read the active document, including popups whose first response was missed.

    Navigation Timing belongs to the current document. A retained response is
    only a fallback for an identical URL (apart from its fragment), never an
    assumption that a new document succeeded.
    """
    from urllib.parse import urldefrag
    state=page.evaluate('''() => ({url:location.href,
        status:performance.getEntriesByType("navigation")[0]?.responseStatus ?? null})''')
    current=page.url
    if state.get('url')!=current:
        return {'http_status':None,'source':'document_changed_during_capture','url':current}
    status=state.get('status')
    if type(status)is int and 100<=status<=599:
        return {'http_status':status,'source':'navigation_timing','url':current}
    if (isinstance(observed,dict)and isinstance(observed.get('url'),str)
        and urldefrag(observed['url'])[0]==urldefrag(current)[0]
        and type(observed.get('http_status'))is int and 100<=observed['http_status']<=599):
        return {'http_status':observed['http_status'],'source':'matching_document_response','url':current}
    return {'http_status':None,'source':'unavailable','url':current}



# Preserve the historical import surface; pure rule shared with the new collectors.
from .task_families.document_health import is_error_document as is_error_document
