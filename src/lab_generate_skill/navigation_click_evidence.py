"""Observe native link activations for tasks explicitly requiring a UI route.

This never clicks, rewrites an action, or exposes the private scoring predicate
in the actor prompt. A final URL alone cannot establish which control was used.
"""
from urllib.parse import urlsplit, unquote, urljoin

SCRIPT = r'''(()=>{
 if(window.__labNavigationClicksInstalled)return;
 window.__labNavigationClicksInstalled=true;
 document.addEventListener('click',event=>{
   if(!event.isTrusted)return;
   const link=event.target instanceof Element?event.target.closest('a[href]'):null;
   if(!link)return;
   const ancestors=[];
   for(let e=link.parentElement;e;e=e.parentElement)
     ancestors.push({tag:e.tagName.toLowerCase(),classes:[...e.classList]});
   void window.__labRecordNavigationClick({source_url:location.href,href:link.href,
      tag:link.tagName.toLowerCase(),label:link.innerText.trim(),target:link.getAttribute('target'),
      classes:[...link.classList],ancestors,trusted:true});
 },true);
})()'''


class NavigationClicks:
    def __init__(self,context):
        self.events=[];self.overflow=False
        context.expose_binding('__labRecordNavigationClick',self.record)
        context.add_init_script(SCRIPT)
        for page in context.pages:page.evaluate(SCRIPT)

    def record(self,source,event):
        # A child frame link is not proof of a main-document navigation control.
        if source['frame']!=source['page'].main_frame:return
        if len(self.events)>=256:self.overflow=True;return
        self.events.append(event)

    def reset(self):
        self.events=[];self.overflow=False

    def snapshot(self):
        return {'events':list(self.events),'overflow':self.overflow,'version':'trusted-native-link-v1'}


def checks(spec,evidence,*,site_origin):
    if (not isinstance(spec,dict) or not isinstance(spec.get('target_path'),str)
        or not spec['target_path'].startswith('/') or not any(spec.get(k)for k in ('link_classes','ancestor_classes'))):
        raise ValueError('Explicit target and native link context required')
    for key in ('link_classes','ancestor_classes'):
        if not isinstance(spec.get(key,[]),list) or any(not isinstance(s,str)or not s for s in spec.get(key,[])):
            raise ValueError('Invalid native link context')
    if (not isinstance(evidence,dict) or evidence.get('version')!='trusted-native-link-v1'
        or type(evidence.get('overflow'))is not bool or not isinstance(evidence.get('events'),list)):
        raise ValueError('Native link event capture missing')
    if evidence['overflow']:raise ValueError('Native link capture overflow')
    origin=urlsplit(site_origin);matched=False
    for event in evidence['events']:
        if (not isinstance(event,dict) or not isinstance(event.get('source_url'),str)
            or not isinstance(event.get('href'),str) or event.get('tag')!='a'
            or event.get('trusted')is not True or not isinstance(event.get('classes'),list)
            or not isinstance(event.get('ancestors'),list)):
            raise ValueError('Malformed native link event')
        source=urlsplit(event['source_url']);target=urlsplit(event['href'])
        if any((u.scheme,u.netloc)!=(origin.scheme,origin.netloc)for u in (source,target)):continue
        if unquote(target.path or '/')!=spec['target_path']:continue
        if not set(spec.get('link_classes',[])).issubset(event['classes']):continue
        required=set(spec.get('ancestor_classes',[]))
        if required and not any(isinstance(a,dict)and isinstance(a.get('classes'),list)and required.issubset(a['classes'])for a in event['ancestors']):continue
        matched=True
    return {'requested_navigation_control_used':matched}


_UNSPECIFIED_TARGET = object()

def control_link(page,selector,origin,target_path,*,label=None,target=_UNSPECIFIED_TARGET):
    """CPU control only: find a unique native link, without fabricating an href."""
    if label is not None and (not isinstance(label,str) or not label.strip()):raise ValueError('Exact public native link label required')
    if target is not _UNSPECIFIED_TARGET and target not in (None,'','_self','_blank'):raise ValueError('Explicit supported native link tab target required')
    matches=[];links=page.locator(selector+':visible');native_origin=urlsplit(origin)
    for i in range(links.count()):
        link=links.nth(i);u=urlsplit(urljoin(page.url,link.get_attribute('href')or''))
        if ((u.scheme,u.netloc)==(native_origin.scheme,native_origin.netloc)and (u.path or '/')==target_path and not u.query and not u.fragment
            and (label is None or link.inner_text().strip()==label)
            and (target is _UNSPECIFIED_TARGET or link.get_attribute('target')==target)):
            matches.append(link)
    if len(matches)!=1:raise ValueError('Native requested link control missing or ambiguous')
    return matches[0]
