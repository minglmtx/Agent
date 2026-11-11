"""Bind only a foreground Admin session to process-level browser integrations."""
from contextlib import contextmanager
import os
import importlib
import sys
from threading import RLock
from urllib.parse import urlsplit

_FOREGROUND=RLock()
PORT_KEYS=('WA_ADMIN_WEB_PORT','WA_ADMIN_DB_PORT','WA_ADMIN_REDIS_PORT',
           'WA_ADMIN_SEARCH_PORT','WA_ADMIN_TRANSPORT_PORT')


def child_port_environment(ports):
    if len(ports)!=5 or len(set(ports))!=5 or any(type(p)is not int or not 1<=p<=65535 for p in ports):
        raise ValueError('Five distinct leased service ports required')
    return {'WA_FIXED_PORTS':' '.join(map(str,ports[:3])),
            'WA_FIXED_SEARCH_PORTS':' '.join(map(str,ports[3:]))}


def validate_endpoints(endpoints,ports):
    child_port_environment(ports)
    if not isinstance(endpoints,dict) or any(not isinstance(k,str) or not k.startswith('WA_')
        or not isinstance(v,str) for k,v in endpoints.items()):
        raise ValueError('Instance endpoint receipt must contain only WA string settings')
    for key,port in zip(PORT_KEYS,ports):
        if endpoints.get(key)!=str(port):raise ValueError('Ready endpoint differs from this instance port lease: '+key)
    u=urlsplit(endpoints.get('WA_SHOPPING_ADMIN',''))
    if (u.scheme,u.hostname,u.port,u.path,u.query,u.fragment)!=('http','127.0.0.1',ports[0],'/admin','',''):
        raise ValueError('Ready Admin URL differs from its private service endpoint')
    return dict(endpoints)


SITE_KEYS=('SHOPPING','SHOPPING_ADMIN','REDDIT','GITLAB','WIKIPEDIA','MAP','HOMEPAGE')
_URL_MODULES=('webarena.browser_env.env_config',
              'webarena.evaluation_harness.helper_functions',
              'webarena.browser_env.auto_login')
_PUBLIC_URLS=dict(zip(SITE_KEYS,('http://onestopmarket.com','http://luma.com/admin',
    'http://reddit.com','http://gitlab.com','http://wikipedia.org',
    'http://openstreetmap.org','http://homepage.com')))


def _set_cached_urls(module, values):
    # Upstream uses `from env_config import SHOPPING_ADMIN`; updating only
    # os.environ or env_config leaves evaluator helpers pointing at an old site.
    for key,value in values.items():
        if hasattr(module,key):setattr(module,key,value)
    if hasattr(module,'URL_MAPPINGS'):
        module.URL_MAPPINGS.clear()
        module.URL_MAPPINGS.update({values[key]:_PUBLIC_URLS[key] for key in
            ('REDDIT','SHOPPING','SHOPPING_ADMIN','GITLAB','WIKIPEDIA','MAP','HOMEPAGE')})
    if module.__name__=='webarena.browser_env.auto_login':
        module.URLS[:]=[values['GITLAB']+'/-/profile',values['SHOPPING']+'/wishlist/',
            values['SHOPPING_ADMIN']+'/dashboard',
            values['REDDIT']+'/user/'+module.ACCOUNTS['reddit']['username']+'/account']


@contextmanager
def activate(endpoints):
    # Background initialization never calls this. Browser and evaluator work
    # using upstream process-global configuration is foreground-only.
    with _FOREGROUND:
        full=all('WA_'+k in endpoints for k in SITE_KEYS)
        keys=set(endpoints)|(set(SITE_KEYS) if full else set())
        previous={k:os.environ.get(k) for k in keys}
        modules={};derived={}
        old_urls={k:os.environ.get(k,os.environ.get('WA_'+k,'todo')) for k in SITE_KEYS}
        for name in _URL_MODULES:
            module=sys.modules.get(name)
            if module is not None:
                modules[name]={k:getattr(module,k) for k in SITE_KEYS if hasattr(module,k)}
                derived[name]={key:(dict(getattr(module,key)) if key=='URL_MAPPINGS' else list(getattr(module,key)))
                               for key in ('URL_MAPPINGS','URLS') if hasattr(module,key)}
                if name==_URL_MODULES[0]:old_urls.update(modules[name])
        try:
            os.environ.update(endpoints)
            if full:
                urls={k:endpoints['WA_'+k] for k in SITE_KEYS}
                os.environ.update(urls)
                importlib.import_module(_URL_MODULES[0])
                for name in _URL_MODULES:
                    module=sys.modules.get(name)
                    if module is not None:_set_cached_urls(module,urls)
            yield
        finally:
            if full:
                # Include helpers first imported by an evaluator in this scope.
                for name in _URL_MODULES:
                    module=sys.modules.get(name)
                    if module is not None:
                        _set_cached_urls(module,old_urls|modules.get(name,{}))
                        for key,value in derived.get(name,{}).items():
                            if key=='URL_MAPPINGS':
                                module.URL_MAPPINGS.clear();module.URL_MAPPINGS.update(value)
                            else:module.URLS[:]=value
            for key,value in previous.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
