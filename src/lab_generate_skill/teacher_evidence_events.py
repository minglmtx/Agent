"""Reversible assistant-record display for an already selected quotes payload.

Each original message occurs once. This layer never pairs observations with
generations, infers environment dispatch, selects pages, or filters attempts.
The original page excerpts remain explicitly lossy. No production caller uses it.
"""
from copy import deepcopy
import json

from .teacher_evidence_pages import digest

VERSION = 'teacher-single-event-view-v1'
GUIDE = '''
Each candidate has one ordered trajectory, with each original message once.
An assistant record displays recorded_action BEFORE model_proposal_text.
recorded_action.value is exactly the original action_payload, not an action
extracted from the proposal. Its state is missing (source field absent), null
(JSON null), empty (empty string), or nonempty (recorded action string).
Missing, null and empty contain no recorded action. Text in model_proposal_text
is the original model response or proposal; it never supplies a missing action.
A nonempty recorded action alone proves neither environment dispatch nor a
successful return. Never infer a tool call from model_proposal_text. Overall
candidate evaluator success does not prove that every individual tool call
succeeded. Read each candidate's evaluator result within its stated task scope.
source_fields retains the assistant's other original fields. Other message
roles, observations, errors, page references and record sources stay unchanged.
Keep candidate and message order; repeated or unpaired messages remain separate.
Structured evaluator feedback is post-execution evidence, not a tool return.
This display layer adds no summary or second chronology. Page excerpts retain
their existing omissions, and historical pages are not current state.
'''

def _require(ok, reason):
    if not ok: raise ValueError(reason)

def _state(message):
    if 'action_payload' not in message: return 'missing'
    value=message['action_payload']
    if value is None: return 'null'
    _require(isinstance(value,str), 'Recorded payload must be original string/null or absent; no coercion')
    return 'nonempty' if value else 'empty'

def _base(base):
    _require(isinstance(base,dict) and base.get('version')=='teacher-evidence-verbatim-quotes-v1'
             and base.get('lossy') is True and base.get('reversible') is False,
             'Previously verified explicit-lossy quotes payload required')
    _require('event_view_version' not in base and 'chronology' not in base
             and 'chronology_version' not in base, 'Do not layer a second chronology or transform twice')
    _require(isinstance(base.get('shared_pages'),list) and isinstance(base.get('evidence'),dict)
             and isinstance(base['evidence'].get('attempts'),list), 'Complete source packet required')
    for attempt in base['evidence']['attempts']:
        _require(isinstance(attempt,dict) and isinstance(attempt.get('trajectory'),list), 'Every candidate trajectory required')
        _require(all(isinstance(m,dict) for m in attempt['trajectory']), 'Every original message must be an object')

def pack(base):
    _base(base)
    output=deepcopy(base); output['event_view_version']=VERSION; bindings=[]
    for i,attempt in enumerate(output['evidence']['attempts']):
        for j,message in enumerate(attempt['trajectory']):
            assistant=message.get('role')=='assistant'
            bindings.append(dict(candidate_index=i,message_index=j,transformed_assistant=assistant,
                original_field_order=list(message),original_message_sha256=digest(message)))
            if not assistant: continue
            action=dict(state=_state(message))
            if 'action_payload' in message: action['value']=deepcopy(message['action_payload'])
            display=dict(role='assistant',recorded_action=action)
            if 'content' in message:
                _require(isinstance(message['content'],str), 'Assistant response text must stay original text')
                display['model_proposal_text']=message['content']
            display['source_fields']={k:deepcopy(v) for k,v in message.items() if k not in ('role','content','action_payload')}
            attempt['trajectory'][j]=display
    audit=dict(version=VERSION,base_sha256=digest(base),derived_sha256=digest(output),messages=bindings,
        this_layer_reversible=True,underlying_pages_lossy=True,pages_selected=False,
        environment_dispatch_inferred=False,production_admitted=False)
    _require(digest(restore(output,audit))==digest(base), 'Display did not restore exact source values/order')
    return output,audit

def restore(derived,audit):
    _require(isinstance(derived,dict) and derived.get('event_view_version')==VERSION
             and isinstance(audit,dict) and audit.get('version')==VERSION, 'Wrong display/audit version')
    _require(audit.get('derived_sha256')==digest(derived), 'Changed display')
    output=deepcopy(derived);del output['event_view_version'];records=audit.get('messages')
    _require(isinstance(records,list), 'Complete message bindings required')
    _base(output);cursor=0
    for i,attempt in enumerate(output['evidence']['attempts']):
        for j,message in enumerate(attempt['trajectory']):
            _require(cursor<len(records), 'Missing original message binding')
            row=records[cursor];cursor+=1
            _require(row.get('candidate_index')==i and type(row.get('candidate_index')) is int
                     and row.get('message_index')==j and type(row.get('message_index')) is int,
                     'Reordered or foreign candidate/message binding')
            assistant=message.get('role')=='assistant'
            _require(row.get('transformed_assistant') is assistant, 'Changed message role')
            if assistant:
                _require(set(message) in ({'role','recorded_action','source_fields'},
                    {'role','recorded_action','model_proposal_text','source_fields'}), 'Ambiguous assistant display fields')
                fields=message['source_fields']; action=message['recorded_action']
                _require(isinstance(fields,dict) and not set(fields)&{'role','content','action_payload'}, 'Conflicting original source fields')
                _require(isinstance(action,dict) and set(action) in ({'state'},{'state','value'}), 'Invalid recorded-action fields')
                restored=deepcopy(fields);restored['role']='assistant'
                if 'model_proposal_text' in message:
                    _require(isinstance(message['model_proposal_text'],str), 'Proposal text changed type')
                    restored['content']=message['model_proposal_text']
                if 'value' in action:restored['action_payload']=deepcopy(action['value'])
                _require(_state(restored)==action.get('state'), 'Payload presence/state/value mismatch')
                order=row.get('original_field_order')
                _require(isinstance(order,list) and len(order)==len(set(order)) and set(order)==set(restored), 'Original field presence changed')
                message={key:restored[key] for key in order};attempt['trajectory'][j]=message
            _require(list(message)==row.get('original_field_order') and digest(message)==row.get('original_message_sha256'), 'Original message changed')
    _require(cursor==len(records) and digest(output)==audit.get('base_sha256'), 'Missing messages or changed non-message evidence')
    return output

def verify(base,derived,audit):
    expected,proof=pack(base)
    # Display order is part of the prompt contract; sorted-key hashes alone
    # cannot prove that recorded_action precedes the proposal text.
    display_bytes=lambda obj:json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
    _require(display_bytes(derived)==display_bytes(expected) and digest(audit)==digest(proof),
             'Display/audit is not the exact ordered source projection')
    return True
