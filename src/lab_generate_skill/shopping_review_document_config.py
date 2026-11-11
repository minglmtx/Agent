"""Public native component config from an existing document response.

Magento consumes/removes text/x-magento-init nodes. Capture the navigation
response already requested by the browser; never issue another HTTP request and
never persist its raw HTML, cookies, form keys or credentials. This component
hook is independent of task/answer/approved-review counts.
"""
from contextlib import contextmanager
import hashlib,re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
import json
from .io_utils import atomic_write_json

VERSION='native-review-document-public-config-v1'


def _document_url(value):
    if not isinstance(value,str):raise ValueError('Public navigation URL required')
    url=urlsplit(value)
    if url.scheme not in('http','https')or not url.netloc or url.username or url.password or url.fragment:
        raise ValueError('Local public document URL required')
    if re.search(r'(?:^|[?&])[^=&]*(?:token|csrf|password|secret|session|form_key)[^=&]*=',url.query,re.I):
        raise ValueError('Sensitive query may not enter public component config')
    return url


def parse_review_document(html,document_url):
    origin=_document_url(document_url)
    if not isinstance(html,str)or not html:raise ValueError('Existing native HTML response body required')
    soup=BeautifulSoup(html,'html.parser');configs=[]
    for node in soup.select('script[type="text/x-magento-init"]'):
        try:data=json.loads(node.get_text())
        except(ValueError,TypeError):continue
        if isinstance(data,dict)and isinstance(data.get('*'),dict)and 'Magento_Review/js/process-reviews'in data['*']:
            configs.append(data['*']['Magento_Review/js/process-reviews'])
    products=soup.select('#product_addtocart_form input[name="product"]')
    if len(configs)!=1 or len(products)!=1:raise ValueError('One native public review config and product identity required')
    cfg=configs[0];ident=products[0].get('value')
    if not isinstance(cfg,dict)or not isinstance(ident,str)or not re.fullmatch('[1-9][0-9]*',ident):raise ValueError('Malformed native public component identity')
    if set(cfg)!={'productReviewUrl','reviewsTabSelector'}or cfg['reviewsTabSelector']!='#tab-label-reviews':
        raise ValueError('Unexpected public native review configuration')
    target=_document_url(cfg['productReviewUrl'])
    if(target.scheme,target.netloc)!=(origin.scheme,origin.netloc):raise ValueError('Native review config leaves the current website')
    result={'version':VERSION,'document_url':document_url,'document_sha256':hashlib.sha256(html.encode()).hexdigest(),
      'public_product_id':ident,'configuration':dict(cfg),'configuration_count':1,'source':'existing_main_frame_navigation_response',
      'extra_http_requests':0,'raw_html_persisted':False,'private_expected_counts_used':False}
    return result


def validate_review_document(config,current_url,public_product_id):
    """Cannot reuse another page/product's source or a private invented config."""
    if config is None:return None
    if not isinstance(config,dict)or set(config)!={'version','document_url','document_sha256','public_product_id','configuration',
      'configuration_count','source','extra_http_requests','raw_html_persisted','private_expected_counts_used'}:
        raise ValueError('Safe existing-document component provenance required')
    if(config['version']!=VERSION or config['source']!='existing_main_frame_navigation_response'
       or type(config['configuration_count'])is not int or config['configuration_count']!=1
       or type(config['extra_http_requests'])is not int or config['extra_http_requests']!=0
       or config['raw_html_persisted']is not False or config['private_expected_counts_used']is not False
       or not isinstance(config['document_sha256'],str)or not re.fullmatch('[0-9a-f]{64}',config['document_sha256'])
       or config['document_url']!=current_url or config['public_product_id']!=public_product_id):
        raise ValueError('Safe public document provenance/identity changed')
    origin=_document_url(current_url);cfg=config['configuration']
    if not isinstance(cfg,dict)or set(cfg)!={'productReviewUrl','reviewsTabSelector'}or cfg['reviewsTabSelector']!='#tab-label-reviews':
        raise ValueError('Native review config changed')
    target=_document_url(cfg['productReviewUrl'])
    if(target.scheme,target.netloc)!=(origin.scheme,origin.netloc):raise ValueError('Component URL is not on this website')
    return config


class ExistingReviewDocument:
    def __init__(self,page,url,capture_path):
        _document_url(url);self.page=page;self.url=url;self.capture_path=capture_path;self.responses=[]
    def observe(self,response):
        try:
            request=response.request
            if request.resource_type=='document'and request.frame==self.page.main_frame and response.url==self.url:
                self.responses.append(response)
        except Exception:return
    def configuration(self):
        record={'version':VERSION,'document_url':self.url,'observed_document_responses':len(self.responses),
           'extra_http_requests':0,'raw_html_persisted':False,'private_expected_counts_used':False}
        try:
            if len(self.responses)!=1:raise ValueError('Exactly one existing main-frame navigation response required')
            response=self.responses[0]
            if response.status!=200:raise ValueError('Native product document did not return HTTP200')
            # response.text reads this cached response. There is no page.request,
            # navigation, fetch or second network operation in this helper.
            config=parse_review_document(response.text(),self.url)
            validate_review_document(config,self.page.url,self.page.evaluate("() => document.querySelector('#product_addtocart_form input[name=product]')?.value||null"))
            record.update(status='captured',public_configuration=config)
            return config
        except Exception as exc:
            record.update(status='needs_diagnosis',diagnostic={'type':type(exc).__name__,'message':str(exc)[:200]})
            raise
        finally:atomic_write_json(self.capture_path,record)


@contextmanager
def capture_review_document(page,url,*,capture_path):
    """Listen only around the caller's one existing navigation; no extra GET."""
    observer=ExistingReviewDocument(page,url,capture_path);page.on('response',observer.observe)
    try:yield observer
    finally:page.remove_listener('response',observer.observe)
