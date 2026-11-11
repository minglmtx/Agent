"""Native expanded cart-item options, an alternative to a full product page.

Only explicitly bound cart-detail goals accept this alternative. Merely opening
the cart, mentioning the product, or expanding a different item is insufficient.
"""
import re
from urllib.parse import urlsplit


def read_cart_details(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      return [...document.querySelectorAll('.minicart-items .product-item')].map(e=>{
        const tab=e.querySelector('[role=tab]');
        const panel=e.querySelector('[role=tabpanel]');
        return {name:e.querySelector('.product-item-name')?.innerText.trim() || '',
          edit_url:e.querySelector('a.edit')?.href || '',
          visible:visible(e), expanded:tab?.getAttribute('aria-expanded')==='true',
          panel_visible:visible(panel),
          options:[...(panel?.querySelectorAll('dt') || [])].map(dt=>({
            label:dt.innerText.trim(), value:dt.nextElementSibling?.innerText.trim() || ''}))};
      });
    }''')


def cart_details_checks(spec, items, *, site_origin):
    if not isinstance(items,list):raise ValueError('Missing native cart detail capture')
    refs=spec.get('cart_options',[])
    if not refs:raise ValueError('Cart option alternatives require native reference values')
    origin=urlsplit(site_origin)
    matches=[]
    for item in items:
        if not isinstance(item,dict):raise ValueError('Malformed cart detail capture')
        for ref in refs:
            edit=urlsplit(item.get('edit_url',''))
            expected=f"/checkout/cart/configure/id/{ref['item_id']}/product_id/{ref['product_id']}/"
            if (edit.scheme,edit.netloc)!=(origin.scheme,origin.netloc) or edit.path!=expected or item.get('name')!=ref['name']:continue
            matches.append((item,ref))
    completed=[(item,ref) for item,ref in matches if item.get('visible') is True
        and item.get('expanded') is True and item.get('panel_visible') is True
        and item.get('options')==ref['options'] and bool(ref['options'])]
    return {'cart_detail_object':bool(matches), 'cart_detail_options_displayed':bool(completed)}


def cart_details_from_saved_ax(text, spec):
    """Recover legacy terminal evidence, never synthesize a new execution.

    Old AX lacks hrefs. Resolve a UNIQUE name against the pinned, unchanged cart;
    require its own dialog/listitem/tab/tabpanel/term/definition hierarchy. The
    caller must verify unchanged cart references and record this provenance.
    """
    lines=text.splitlines()
    def subtree(i):
        indent=len(lines[i])-len(lines[i].lstrip());end=i+1
        while end<len(lines) and len(lines[end])-len(lines[end].lstrip())>indent:end+=1
        return lines[i+1:end]
    def role(line):return re.sub(r'^\s*(?:\[[^\]]+\]\s*)?','',line)
    def static(block):
        values=[]
        for line in block:
            m=re.fullmatch(r"StaticText '((?:\\.|[^'])*)'",role(line))
            if m:values.append(m[1])
        return ' '.join(values)
    dialogs=[subtree(i) for i,l in enumerate(lines) if role(l).startswith('dialog ')]
    result=[]
    for dialog in dialogs:
        if not any("button 'Proceed to Checkout'" in l for l in dialog):continue
        # Subtree helper works on the complete input, preserving exact nesting.
        indices=[i for i,l in enumerate(lines) if l in dialog and role(l).startswith('listitem ')]
        for i in indices:
            block=subtree(i)
            names=[r for r in spec['cart_options'] if any(role(l)=="link '"+r['name']+"'" for l in block)]
            if len(names)!=1:continue
            ref=names[0]
            expanded=any(role(l).startswith("tab 'See Details") and 'expanded=True' in l for l in block)
            panels=[j for j,l in enumerate(lines) if l in block and role(l).startswith('tabpanel ')]
            pairs=[]
            for j in panels:
                panel=subtree(j);label=None
                for k,l in enumerate(lines):
                    if l not in panel:continue
                    if role(l).startswith('term '):label=static(subtree(k))
                    elif role(l).startswith('definition ') and label:
                        pairs.append({'label':label,'value':static(subtree(k))});label=None
            result.append({'name':ref['name'],'item_id':ref['item_id'],'product_id':ref['product_id'],
                'visible':True,'expanded':expanded,'panel_visible':bool(panels),'options':pairs})
    return result


FEEDBACK={'cart_detail_object':'The cart item is one of the objects allowed by the task.',
          'cart_detail_options_displayed':'Its native item details are expanded and the stored option values are displayed.'}
