"""Observe native Recently Ordered submission origin; never operate the actor.

The cart delta alone cannot prove a task's explicit source surface. Preserve
trusted native submit evidence separately from terminal persisted cart state.
No form key, cookies, request headers, private task ID or action plan is logged.
"""
from decimal import Decimal
from urllib.parse import urlsplit
from .shopping_recent_items import READ, validate as validate_recent, checks as recent_checks

VERSION='native-recent-cart-submit-v1'

SCRIPT=r"""(()=>{
 if(window.__labRecentCartInstalled)return;
 window.__labRecentCartInstalled=true;
 let activatedForm=null,activationTime=0;
 function activate(event){
   if(!event.isTrusted || !(event.target instanceof Element))return;
   let form=null;
   if(event.type==='click'){
     const button=event.target.closest('button[type="submit"],button:not([type]),input[type="submit"]');
     form=button?.form||null;
   }else if(event.key==='Enter')form=event.target.closest('form');
   if(form?.closest('.block-reorder')){activatedForm=form;activationTime=performance.now();}
 }
 document.addEventListener('click',activate,true);
 document.addEventListener('keydown',activate,true);
 document.addEventListener('submit',event=>{
   const form=event.target;
   if(!event.isTrusted || !(form instanceof HTMLFormElement) || activatedForm!==form || performance.now()-activationTime>1500)return;
   activatedForm=null;
   const block=form.closest('.block-reorder');
   if(!block || block.querySelector('#block-reorder-heading')?.innerText.trim()!=='Recently Ordered')return;
   const state=("""+READ+r""")();
   const selected=[...form.querySelectorAll('input[type="checkbox"][name="order_items[]"]:checked')].map(e=>e.value);
   const action=new URL(form.action,location.href);
   void window.__labRecordRecentCart({trusted:true,source_url:location.origin+location.pathname,
      method:form.method.toUpperCase(),action_url:action.origin+action.pathname,
      selected_order_item_ids:selected,public_widget:state});
 },true);
})()"""


class RecentCartSubmissions:
    def __init__(self,context):
        self.events=[];self.overflow=False
        context.expose_binding('__labRecordRecentCart',self.record)
        context.add_init_script(SCRIPT)
        for page in context.pages:page.evaluate(SCRIPT)

    def record(self,source,event):
        if source['frame']!=source['page'].main_frame:return
        if len(self.events)>=64:self.overflow=True;return
        self.events.append(event)

    def reset(self):self.events=[];self.overflow=False

    def snapshot(self):
        return {'version':VERSION,'events':list(self.events),'overflow':self.overflow}


def validate(cart):
    source=cart.get('source_surface')
    if not isinstance(source,dict) or set(source)!={'kind','items','selected_order_item_ids'} or source['kind']!='recent_ordered':
        raise ValueError('Explicit native Recently Ordered surface required')
    validate_recent({'items':source['items']})
    ids=source['selected_order_item_ids']
    if not isinstance(ids,list) or not ids or any(type(x)is not int or x<=0 for x in ids) or len(ids)!=len(set(ids)):
        raise ValueError('Explicit distinct recent order items required')
    mapping={r['order_item_id']:r for r in source['items']}
    products=cart.get('products',[])
    if cart.get('operation')!='add_products' or not set(ids)<=mapping.keys() or len(products)!=len(ids):
        raise ValueError('Recent selection and cart products differ')
    requested=sorted((r['product_id'],r['product_name'],r['product_path'],Decimal(str(r['quantity']))) for r in products)
    expected=sorted((mapping[i]['product_id'],mapping[i]['name'],mapping[i]['product_path'],Decimal(1)) for i in ids)
    if requested!=expected:raise ValueError('Native recent form adds one of each selected order item')


def checks(cart,evidence,*,site_origin):
    validate(cart)
    if not isinstance(evidence,dict) or evidence.get('version')!=VERSION or type(evidence.get('overflow'))is not bool or not isinstance(evidence.get('events'),list):
        raise ValueError('Missing native recent-submit evidence')
    if evidence['overflow']:raise ValueError('Native recent-submit event capture overflow')
    source=cart['source_surface'];expected=sorted(str(x)for x in source['selected_order_item_ids'])
    origin=urlsplit(site_origin);matched=False
    for event in evidence['events']:
        if (not isinstance(event,dict) or type(event.get('trusted'))is not bool or not isinstance(event.get('source_url'),str)
                or not isinstance(event.get('action_url'),str) or not isinstance(event.get('method'),str)
                or not isinstance(event.get('selected_order_item_ids'),list) or 'public_widget'not in event):
            raise ValueError('Malformed native recent-submit event')
        start=urlsplit(event['source_url']);action=urlsplit(event['action_url'])
        if any((u.scheme,u.netloc)!=(origin.scheme,origin.netloc)for u in (start,action)):continue
        if (event['trusted']is not True or event['method']!='POST' or action.path.rstrip('/')!='/checkout/cart/addgroup'
                or action.query or action.fragment):continue
        selected=event['selected_order_item_ids']
        if any(not isinstance(x,str)for x in selected) or sorted(selected)!=expected:continue
        widget=event['public_widget']
        if not isinstance(widget,dict) or not isinstance(widget.get('url'),str):
            raise ValueError('Missing native recent-submit widget URL')
        current=urlsplit(widget['url'])
        if (current.scheme,current.netloc,current.path)!=(start.scheme,start.netloc,start.path):continue
        public=recent_checks({'items':source['items']},widget,site_origin=site_origin)
        # Native Magento also renders this component on category and order
        # history pages. Cart goals identify the component, not its page route.
        # Keep account-page checks unchanged for the separate view-only task.
        if all(value for key,value in public.items() if key!='recent_items_account_page'):matched=True
    return {'requested_recent_source_used':matched}


FEEDBACK={'requested_recent_source_used':'The requested products were submitted from the native Recently Ordered component of the current account.'}
