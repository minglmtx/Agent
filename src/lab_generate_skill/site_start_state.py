"""Explicit expected native error starts, distinct from terminal success checks."""
from urllib.parse import urlsplit
from .site_navigation_rules import valid_initial_page


def valid_task_start(contract, page, *, site_origin):
    policy=contract.get('initial_page_policy')
    if policy is None:return valid_initial_page(page,site_origin=site_origin)
    if policy.get('kind')!='native_missing_resource':raise ValueError('Unsupported initial-page policy')
    if not isinstance(page,dict):return False
    actual=urlsplit(page.get('url') or '');origin=urlsplit(site_origin)
    path=policy.get('path');link=policy.get('required_link_path')
    if not isinstance(path,str) or not isinstance(link,str) or any(not v.startswith('/') or v.startswith('//') for v in (path,link)):
        raise ValueError('Explicit local missing-resource path and recovery link required')
    return (type(page.get('http_status')) is int and page['http_status']==404
            and (actual.scheme,actual.netloc)==(origin.scheme,origin.netloc)
            and actual.path==path and not actual.query and page.get('login_page') is False
            and link in page.get('local_link_paths',[]))


def local_link_paths(page,site_origin):
    origin=urlsplit(site_origin)
    return sorted({urlsplit(href).path for href in page.locator('a[href]').evaluate_all('es=>es.map(e=>e.href)')
                   if (urlsplit(href).scheme,urlsplit(href).netloc)==(origin.scheme,origin.netloc)})
