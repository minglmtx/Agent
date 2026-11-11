"""Read product cards from the same BrowserGym DOM/AX observation, offline.

No page.evaluate, page wait, database query or observation modification occurs.
Ambiguous DOM/AX pairs are evidence gaps, never silently omitted products.
"""
from urllib.parse import urljoin


def require(value,message):
    if not value:raise ValueError(message)


def cards_from_raw(raw):
    dom=raw['dom_object'];strings=dom['strings'];docs=dom['documents']
    require(docs,'Missing DOM document')
    doc=docs[0];nodes=doc['nodes'];count=len(nodes['parentIndex'])
    for key in ('nodeName','nodeType','nodeValue','attributes','backendNodeId'):
        require(len(nodes[key])==count,'Incomplete DOM node arrays')
    require(strings[doc['documentURL']]==raw['url'],'Main DOM and actual observation URL differ')
    attrs=[];children=[[]for _ in range(count)]
    for index,values in enumerate(nodes['attributes']):
        require(len(values)%2==0,'Malformed DOM attribute list')
        attrs.append({strings[values[i]]:strings[values[i+1]]for i in range(0,len(values),2)})
        parent=nodes['parentIndex'][index]
        require(parent==-1 or 0<=parent<index,'DOM parent order/cycle differs')
        if parent>=0:children[parent].append(index)
    def descendants(index):
        result=[];queue=list(reversed(children[index]))
        while queue:
            child=queue.pop();result.append(child);queue.extend(reversed(children[child]))
        return result
    def text(index):
        return ''.join(strings[nodes['nodeValue'][i]]for i in [index]+descendants(index)if nodes['nodeType'][i]==3).strip()
    def classes(index):return set(attrs[index].get('class','').split())
    layout=doc['layout'];laid_out={i for i,b in zip(layout['nodeIndex'],layout['bounds'])if len(b)==4 and b[2]>0 and b[3]>0}
    ax={}
    for n in raw['axtree_object']['nodes']:
        if not n.get('ignored') and n.get('backendDOMNodeId') is not None:
            ax.setdefault(n['backendDOMNodeId'],[]).append(n)
    def ax_names(index,role):
        return [n.get('name',{}).get('value','')for n in ax.get(nodes['backendNodeId'][index],[])if n.get('role',{}).get('value')==role]
    def wrapper(index):
        index=nodes['parentIndex'][index]
        while index>=0:
            if {'products','wrapper'}<=classes(index):return index
            index=nodes['parentIndex'][index]
        return None
    cards=[]
    for index in range(count):
        if strings[nodes['nodeName'][index]].upper()!='LI' or 'product-item'not in classes(index):continue
        root=wrapper(index)
        if root is None or index not in laid_out or root not in laid_out:continue
        sub=descendants(index)
        links=[i for i in sub if 'product-item-link'in classes(i)]
        boxes=[i for i in sub if attrs[i].get('data-price-type')=='finalPrice']
        identities={attrs[i]['data-product-id']for i in sub if 'data-product-id'in attrs[i]}
        require(len(links)==len(boxes)==1 and len(identities)==1,'Ambiguous or missing product-card structure')
        link=links[0];box=boxes[0];names=ax_names(link,'link')
        require(len(names)==1 and names[0] and link in laid_out and box in laid_out,'Displayed card lacks matching AX link or layout')
        require(' '.join(text(link).split())==' '.join(names[0].split()),'DOM/AX product-name disagreement')
        price=text(box);price_ax=[]
        for child in [box]+descendants(box):price_ax.extend(ax_names(child,'StaticText'))
        require(price and price in price_ax,'DOM price lacks exact same-subtree AX text')
        identity=next(iter(identities));require(identity.isdigit() and int(identity)>0,'Native product identity missing')
        require(attrs[link].get('href') and attrs[box].get('data-price-amount')is not None,'Native URL/price attribute missing')
        cards.append(dict(id=identity,name=names[0],url=urljoin(raw['url'],attrs[link]['href']),
            name_visible=True,price_visible=True,price_text=price,price_attribute=attrs[box]['data-price-amount']))
    require(len(cards)==len({c['id']for c in cards}),'Duplicate visible product card')
    return cards
