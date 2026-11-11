"""Account tasks can start on native documents as well as map canvases.

A document start must not be forced through the map-view readiness protocol.
These checks do not authenticate, navigate elsewhere, or test task completion.
"""
from urllib.parse import urlsplit
from .map_candidate_start import validate_initial
from .map_view import wait_native_view
from .site_navigation_rules import valid_initial_page


def validate_document_start(candidate,origin,state):
    expected=urlsplit(origin+candidate['start_path']);actual=urlsplit(state.get('url',''))
    if actual!=expected or not valid_initial_page(state,site_origin=origin):
        raise ValueError('Declared native document start unavailable')
    if not state.get('native_header')or not state.get('headings')or not state.get('content','').strip():
        raise ValueError('Native document content missing')
    return True


def observe_account_start(page,candidate,origin,http_status):
    path=urlsplit(candidate['start_path']).path
    if path in ('/','/search','/directions'):
        from .map_route import read_route
        view=wait_native_view(page,candidate['start_path'])
        route=read_route(page)if 'route='in candidate['start_path']else None
        validate_initial(candidate,origin,page.url,view,route)
        return dict(kind='map',url=page.url,view=view,route=route)
    state=page.evaluate('''() => {
      const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=="hidden";
      const content=document.querySelector("#content");
      const headings=[...document.querySelectorAll("h1")].filter(visible).map(e=>e.innerText.trim()).filter(Boolean);
      return {url:location.href,title:document.title,headings:headings,
        content:visible(content)?content.innerText:"",native_header:visible(document.querySelector("header")),
        login_page:visible(document.querySelector("#login_form")),
        error_page:headings.some(h=>/^(404|500|page not found|internal server error|application error)/i.test(h))};
    }''')
    state['http_status']=http_status
    validate_document_start(candidate,origin,state)
    return dict(kind='document',**state)
