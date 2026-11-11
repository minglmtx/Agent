"""Identify a captured pre-fetch input rejection without changing its HTTP result."""
import ast,json

SOURCE='cb16efd063fc41a3f9d5'
ENTRY='/__lab_local__/reader'
ERROR='Feed escaped the declared native origin'
PUBLIC_ERROR='Could not load or save the feed.'


def confirmed(events,trace,contract,origin):
    """Require exact owned-reader cause and actual form submission observations.

The qualified ReaderUI invokes native_url on the submitted value before fetch.
This is not a general ValueError/502 exemption. Missing or different evidence
returns False and remains an unresolved runtime/evidence error.
"""
    try:
        from .rss_client import native_url
        if not isinstance(events,list) or any(not isinstance(e,dict) for e in events):
            return False
        errors=[e for e in events if e.get('event')=='request_error']
        if errors!=[dict(event='request_error',type='ValueError',message=ERROR)]:
            return False
        if any(e.get('event') not in ('reader_reopened','subscription_request','request_error') for e in events):
            return False
        if not isinstance(contract,dict) or contract.get('source_task_id')!=SOURCE:
            return False
        if not isinstance(trace,dict) or trace.get('error') is not None or trace.get('task_id')!=contract['task_id'] or trace.get('task_instruction')!=contract['goal']:
            return False
        messages=trace['messages']
        if not isinstance(messages,list) or trace['rounds']!=sum(m.get('role')=='assistant' for m in messages):
            return False
        observed=None;pending=None;waiting=False;matched=0
        for message in messages:
            if message.get('role')=='user':
                observed=json.loads(message['content'])
                if waiting:
                    if observed.get('url')!=origin+ENTRY or observed.get('last_action_error') or PUBLIC_ERROR not in observed.get('axtree_txt',''):
                        return False
                    matched+=1;waiting=False
                continue
            if message.get('role')!='assistant' or not isinstance(observed,dict):
                continue
            payload=message.get('action_payload')
            if not isinstance(payload,str):
                pending=None
                continue
            call=ast.parse(payload,mode='eval').body
            if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name) or call.keywords:
                return False
            name=call.func.id;args=[ast.literal_eval(a) for a in call.args]
            tree=observed.get('axtree_txt','')
            on_form=observed.get('url')==origin+ENTRY and not observed.get('last_action_error')
            if name=='fill' and len(args)==2 and all(isinstance(a,str) for a in args):
                pending=None
                bid,value=args
                if on_form and ('['+bid+"] textbox 'Feed URL'") in tree:
                    try:native_url(value,origin)
                    except ValueError as error:
                        if str(error)==ERROR:pending=(bid,value)
            elif pending and name=='click' and len(args)==1 and isinstance(args[0],str):
                bid,value=pending;pending=None
                if on_form and ('['+bid+"] textbox 'Feed URL' value="+repr(value)) in tree and ('['+args[0]+"] button 'Subscribe'") in tree:
                    waiting=True
            else:
                pending=None
        return matched==1 and not waiting
    except (ValueError,KeyError,TypeError,SyntaxError,AttributeError):
        return False
