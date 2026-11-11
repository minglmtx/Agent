"""Read-only NY diary candidate: actual identified entries in list or detail."""
from urllib.parse import unquote, urlsplit
import re

VERSION='native-map-ny-diary-read-v187'
READ=r'''() => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=="hidden";
 return {url:location.href,entries:[...document.querySelectorAll('.diary_post')].filter(visible).map(e=>{
   const heading=e.querySelector('h2 a');const body=e.querySelector('.richtext');
   return {url:heading?.href||'',title:heading?.innerText||'',body:visible(body)?body.innerText:'',text:e.innerText};
 })};
}'''


def evaluate(reference, observations, terminal, *, origin, native_unchanged, runtime_error=None):
    def unknown(why):return dict(version=VERSION,status='unknown',reward=None,reason=why)
    try:
        if runtime_error or native_unchanged is not True:
            return unknown('Native capture, runtime or read-only state changed')
        if (terminal.get('http_status')!=200 or terminal.get('error_page')is not False
                or terminal.get('login_page')is not False):
            return unknown('Current native document is unhealthy or missing')
        root=urlsplit(origin);end=urlsplit(terminal['url'])
        if (end.scheme,end.netloc)!=(root.scheme,root.netloc):return unknown('Native document origin differs')
        targets=reference['entries']
        if not targets or any(type(r['id'])is not int or r['id']<=0 or r['region']!='New York City'
                              or not r['title'] or not r['body'] or not r['author'] for r in targets):
            return unknown('Native NYC diary reference is incomplete')
        # A label or query string alone cannot establish a real regional query.
        # This shipped site has no generic city-filtered diary endpoint.
        matched=False
        for observation in observations:
            if observation.get('url')!=terminal['url'] or not isinstance(observation.get('actual_public_text'),str):continue
            for shown in observation.get('entries',[]):
                target=urlsplit(shown.get('url',''))
                if (target.scheme,target.netloc)!=(root.scheme,root.netloc) or target.query or target.fragment:continue
                for row in targets:
                    path='/user/'+row['author']+'/diary/'+str(row['id'])
                    if (unquote(target.path)==path and shown.get('title')==row['title'] and shown.get('body')==row['body']
                            and all(s in observation['actual_public_text'] for s in (row['title'],row['body'],row['author']))):
                        matched=True
        return dict(version=VERSION,status='success'if matched else'failure',reward=float(matched),
                    checks=dict(native_nyc_entry_actually_seen=matched),
                    excluded_followup_actions=True)
    except(KeyError,TypeError,ValueError)as error:return unknown(str(error))
