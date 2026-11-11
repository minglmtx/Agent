"""Record what a transient browser bid referred to when the action was attempted."""
import ast
import re


def observed_targets(action, observation):
    node=ast.parse(action,mode='eval').body
    if node.func.id not in {'click','dblclick','hover','focus','clear','fill','select_option','press','drag_and_drop','upload_file'}:
        return []
    count=2 if node.func.id=='drag_and_drop' else 1
    targets=[]
    for argument in node.args[:count]:
        bid=ast.literal_eval(argument)
        if not isinstance(bid,str):continue
        match=re.search(r'^\s*\['+re.escape(bid)+r'\][^\n]*',observation.get('axtree_txt',''),re.MULTILINE)
        if match:targets.append({'bid':bid,'observed_node':match.group(0).strip()})
    return targets
