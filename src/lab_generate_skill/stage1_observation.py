"""Narrow, versioned preprocessing for the official admin navigation pilot.

Keep all semantic text. Remove ephemeral element IDs for the skill generator and
canonicalize only tied Bestsellers rows. Actor observations are never transformed.
"""
import re

ADMIN_NAVIGATION = 'webarena157-bestseller-ties-v1'


def initial_view(text, policy='identity', env_id=''):
    if policy=='identity':return text
    if policy!=ADMIN_NAVIGATION or env_id.removeprefix('browsergym/')!='webarena.157':
        raise ValueError('Observation normalization is restricted to official navigation task 157')
    root={'line':'','depth':-1,'children':[]};stack=[root]
    for raw in text.splitlines():
        depth=len(raw)-len(raw.lstrip('\t'))
        line=re.sub(r'^\[\d+\]\s*','',raw.lstrip('\t'))
        node={'line':line,'depth':depth,'children':[]}
        while stack[-1]['depth']>=depth:stack.pop()
        stack[-1]['children'].append(node);stack.append(node)
    def render(node):
        lines=[] if node is root else ['\t'*node['depth']+node['line']]
        for child in node['children']:lines.extend(render(child))
        return lines
    def visit(node,bestsellers=False):
        bestsellers=bestsellers or (node['line'].startswith('tabpanel ') and 'Bestsellers' in node['line'])
        for child in node['children']:visit(child,bestsellers)
        if not bestsellers:return
        children=node['children']
        def quantity(row):
            if not row['line'].startswith('row '):return None
            cells=row['children']
            if len(cells)!=3 or any(not c['line'].startswith('gridcell ') for c in cells):return None
            match=re.fullmatch(r"gridcell '(\d+)'",cells[-1]['line'])
            return match.group(1) if match else None
        i=0
        while i<len(children):
            value=quantity(children[i]);j=i+1
            if value is not None:
                while j<len(children) and quantity(children[j])==value:j+=1
                children[i:j]=sorted(children[i:j],key=lambda n:'\n'.join(render(n)))
            i=j
    visit(root)
    return '\n'.join(render(root))
