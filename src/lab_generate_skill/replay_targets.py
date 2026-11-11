"""Diagnostic-only AX subtree matching. Never rewrites a live actor action."""
import ast
import re


def signatures(observation):
    lines=observation.get('axtree_full_txt',observation.get('axtree_txt','')).splitlines();result={}
    for i,line in enumerate(lines):
        m=re.match(r'(\s*)\[([^\]]+)\]\s*(.*)',line)
        if not m:continue
        indent=len(m[1]);end=i+1
        while end<len(lines) and len(lines[end])-len(lines[end].lstrip())>indent:end+=1
        subtree=tuple((len(l)-len(l.lstrip())-indent,re.sub(r'^\[[^\]]+\]\s*','',l.strip())) for l in lines[i:end])
        result[m[2]]=subtree
    return result


def remap_exact_subtree(action,old,current):
    call=ast.parse(action,mode='eval').body
    if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name):raise ValueError('Expected one action call')
    if call.func.id not in {'click','dblclick','fill','select_option','press','hover','focus','clear','upload_file'}:
        return action,[]
    bid=ast.literal_eval(call.args[0]);before=signatures(old);after=signatures(current)
    if bid not in before:raise ValueError('Recorded bid missing from original observation')
    matches=[k for k,v in after.items() if v==before[bid]]
    if len(matches)!=1:raise ValueError('Recorded subtree does not have a unique current match')
    call.args[0]=ast.Constant(matches[0])
    return ast.unparse(call),[{'recorded_bid':bid,'current_bid':matches[0],'method':'exact_public_ax_subtree','subtree_nodes':len(before[bid])}]
