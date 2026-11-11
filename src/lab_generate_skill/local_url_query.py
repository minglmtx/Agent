"""Deployment-independent private URL references with strict live-origin checks."""
from urllib.parse import urlsplit, parse_qsl
import copy


def same_local_url(actual,expected,site_origin):
    if any(not isinstance(v,str) or not v for v in (actual,expected,site_origin)):
        return False
    # Do not silently normalize browser control characters, credentials, a
    # protocol-relative host, encoded path aliases, or an unrelated public host.
    if any(ch.isspace() or ord(ch)<32 for v in (actual,expected,site_origin) for ch in v):return False
    try:
        a,e,o=map(urlsplit,(actual,expected,site_origin))
        if (o.scheme not in ('http','https') or not o.hostname or o.username or o.password or o.path not in ('','/') or o.query or o.fragment
                or a.scheme!=o.scheme or a.hostname!=o.hostname or a.port!=o.port or a.username or a.password
                or e.scheme or e.netloc or not e.path.startswith('/') or e.path.startswith('//')):return False
        # Duplicate parameters, even identical ones, are not part of the native
        # share-link protocol. Query order itself is immaterial.
        aq,eq=parse_qsl(a.query,keep_blank_values=True),parse_qsl(e.query,keep_blank_values=True)
        if len({k for k,v in aq})!=len(aq) or len({k for k,v in eq})!=len(eq):return False
        return a.path==e.path and sorted(aq)==sorted(eq) and a.fragment==e.fragment
    except (ValueError,TypeError):return False


def negative_url_names(query):
    return ['url_'+case+'_'+key for key,kind in query['fields'].items() if kind=='local_url'
            for case in ('wrong_origin','relative','wrong_path')]


def negative_url_answers(query,values,site_origin):
    if not negative_url_names(query):return {}
    origin=site_origin.rstrip('/')
    positive=copy.deepcopy(values)
    for key,kind in query['fields'].items():
        if kind=='local_url':positive[key]=origin+values[key]
    answers={}
    for key,kind in query['fields'].items():
        if kind!='local_url':continue
        for case,value in [('wrong_origin','https://unrelated.invalid'+values[key]),
                           ('relative',values[key]),('wrong_path',origin+'/nonexistent-share-link-control')]:
            answer=copy.deepcopy(positive);answer[key]=value
            answers['url_'+case+'_'+key]=answer
    return answers
