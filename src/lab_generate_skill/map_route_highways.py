"""Candidate exact numbered-highway readout from the complete native car route.

The public derivative must ask for numbered road references actually traversed,
excluding exit-sign destinations. Merely mentioning a highway in instructions
is not traversal evidence. No expected answer is returned in evaluator feedback.
"""
import re
from .map_route_print import require_reference
from .map_route_normal_capture import terminal_checks
VERSION='native-numbered-route-highways-v1'
_PATTERN=re.compile(r'([A-Z]{1,3})[ -]*(\d+[A-Z]?)')


def canonical(value):
    if not isinstance(value,str):raise ValueError('Text highway reference required')
    m=_PATTERN.fullmatch(value.strip().upper())
    if not m:raise ValueError('A complete numbered highway reference required')
    return m[1]+' '+m[2]


def reference_highways(reference):
    rows=require_reference(reference)
    if reference['profile']!='car':raise ValueError('Explicit driving route reference required')
    result=set()
    for step in reference['native_body']['routes'][0]['legs'][0]['steps']:
        raw=step.get('ref','')
        if not isinstance(raw,str):raise ValueError('Native road reference malformed')
        for part in filter(None,(v.strip()for v in raw.split(';'))):
            if not any(c.isdigit()for c in part):continue  # e.g. named parkways FDR/HR
            value=canonical(part)
            prefix,number=value.split(' ')
            visible=re.compile(r'(?<![A-Za-z0-9])'+re.escape(prefix)+r'[ -]*'+re.escape(number)+r'(?![A-Za-z0-9])')
            if not any(visible.search(row)for row in rows):raise ValueError('Private road reference is not in public native instructions')
            result.add(value)
    if not result:raise ValueError('Declared route has no numbered highway references')
    return sorted(result)


def evaluate(reference,*,served,state,url,answer,runtime_error=None,integrity=True):
    checks={}
    def result(status,reason):return dict(version=VERSION,status=status,reward=None if status=='unknown'else float(status=='success'),checks=checks,reason=reason)
    if runtime_error or integrity is not True:return result('unknown','Runtime or state integrity unavailable.')
    try:
        expected=set(reference_highways(reference))
        checks.update(terminal_checks(reference['scope'],served,reference['native_body'],state,url))
    except (ValueError,KeyError,TypeError):return result('unknown','Independent native route evidence is incomplete.')
    if not all(checks.values()):return result('failure','The requested complete driving route is not displayed.')
    checks['declared_answer_schema']=isinstance(answer,dict)and set(answer)=={'highway_refs'}and isinstance(answer['highway_refs'],list)
    if not checks['declared_answer_schema']:return result('failure','Answer does not follow the declared highway_refs list schema.')
    try:actual=[canonical(v)for v in answer['highway_refs']]
    except ValueError:return result('failure','Answer contains an invalid numbered highway reference.')
    checks['distinct_highways']=len(actual)==len(set(actual))
    checks['complete_traversed_highway_set']=set(actual)==expected
    return result('success'if all(checks.values())else 'failure','Checked all numbered road references on the displayed driving route, excluding exit-sign destinations.')
