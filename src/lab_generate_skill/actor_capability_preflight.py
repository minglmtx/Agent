"""Cheap actor/browser capability agreement before website or model allocation.

Run from the exact submitted runtime. Browser-only control probes cannot prove
that the generator's schema and parser expose an optional browser operation.
"""
import json
from .actor_protocol import ActorProtocol
from .constrained_actions import action_output_schema


def require_capabilities(contract):
    capabilities=contract.get('browser_capabilities',{})
    if capabilities.get('print_to_pdf')is not True:return
    protocol=ActorProtocol('structured_observed')
    obs=dict(axtree_txt='',browser_capabilities=dict(print_to_pdf=True))
    action=json.dumps(dict(action='print_page',args=[]))
    try:
        enabled=action_output_schema(print_to_pdf=True)['properties']['action']['enum']
        disabled=action_output_schema()['properties']['action']['enum']
        assert 'print_page'in enabled and 'print_page'not in disabled
        assert protocol.parse(action,obs)[0]=='print_page()'
        assert 'print_page()'in protocol.messages('Print the current page',obs,[])[0]['content']
        try:protocol.parse(action,{})
        except ValueError:pass
        else:raise AssertionError('Print action enabled without declared capability')
    except (AssertionError,KeyError,TypeError,ValueError)as exc:
        raise ValueError('Submitted actor prompt/schema/parser do not match print-capable browser')from exc
