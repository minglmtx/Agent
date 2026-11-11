"""Narrow Magento form-protocol feedback, NOT a task-success evaluator.

Only observed control labels, executed edit/submit order and explicit page messages
are used. Unknown states stay unknown. No goal parsing, expected answers, or DB reads.
"""
import ast
import re


def form_progress(observation,history):
    text=observation.get('axtree_txt','')
    dirty=False;submitted=False
    for row in history:
        if row.get('error')=='invalid_action_format':continue
        try:call=ast.parse(row['action'],mode='eval').body;name=call.func.id
        except (KeyError,ValueError,SyntaxError,AttributeError):continue
        # A failed browser edit cannot establish that the form changed.
        if name in ('fill','select_option','clear') and not row.get('last_action_error'):
            dirty=True;submitted=False
        if name=='click':
            labels=[t['observed_node'] for t in row.get('targets',[])]
            if any(re.search(r"\bbutton '(?:Save|Submit(?: Comment)?)'(?:,|$)",label) for label in labels):
                submitted=True
    validation=re.search(r"(?:StaticText|alert) '[^\n]*(?:Please enter a number|Invalid numeric value|Validation failed)[^\n]*",text,re.I)
    unsaved=re.search(r"StaticText '[^\n]*Unsaved changes[^\n]*",text,re.I)
    saved=re.search(r"StaticText '(?:You saved the product\.|Changes saved\.?)'",text,re.I)
    if dirty and validation:
        return {'state':'save_failed','reason':validation.group(0).strip(),'finish_allowed':False}
    if dirty and (unsaved or not submitted):
        return {'state':'unsaved','reason':'Observed edits have no subsequent observed Save/Submit action, or the page explicitly says Unsaved changes.','finish_allowed':False}
    if dirty and submitted and saved:
        return {'state':'save_acknowledged','reason':saved.group(0).strip(),'finish_allowed':True}
    return {'state':'unknown','reason':'No decisive form-protocol signal; this is not a task-success judgment.','finish_allowed':True}
