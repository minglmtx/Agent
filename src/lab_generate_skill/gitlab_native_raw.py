"""Select an actually advertised same-origin native Raw control.

GitLab advertises both a plain Raw link and an inline=false download for the
same blob. Duplicate controls do not make that one public object ambiguous.
This function performs no request and never synthesizes an unadvertised link.
"""
from urllib.parse import urlsplit,urljoin,unquote


def native_raw_url(links,expected_path,origin):
    base=urlsplit(origin)
    if base.scheme not in ('http','https')or not base.netloc or base.username or base.password:raise ValueError('Invalid local origin')
    candidates=[]
    for link in links:
        if not isinstance(link,dict)or not isinstance(link.get('href'),str):raise ValueError('Malformed native Raw capture')
        url=urljoin(origin.rstrip('/')+'/',link['href']);parsed=urlsplit(url)
        if parsed.username or parsed.password or(parsed.scheme,parsed.netloc)!=(base.scheme,base.netloc):continue
        if unquote(parsed.path)==expected_path:
            candidates.append(url)
    unique=sorted(set(candidates),key=lambda url:(bool(urlsplit(url).query),url))
    return unique[0]if unique else None
