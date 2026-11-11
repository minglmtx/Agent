"""Optional chronology for the offline Teacher quotes candidate.

This adds source-bound labels, never an inferred outcome, missing action, count
summary or model-written explanation. The underlying candidate is unchanged.
There is no production caller, token fallback, dispatch or file access here.
"""
from copy import deepcopy
import json

from .action_history import observed_targets
from .teacher_evidence_pages import PAGE_FIELDS, digest
from .teacher_evidence_quotes import VERSION as QUOTES_VERSION, _discover, _unique_object

VERSION = 'teacher-evidence-explicit-chronology-v1'
GUIDE = '''
chronology gives every candidate's own ordered generation records. Candidate
and message indices are zero-based. action_payload is the recorded submitted
action; assistant content is a model proposal and may contain an invalid action.
"no_nonempty_action_recorded" means that generation has no nonempty recorded
action payload; do not turn text in its response into an executed action.
"nonempty_action_recorded" does not establish successful execution or task
completion. The next observation's error fields are copied exactly, including
empty strings. A missing error field is unknown, not a successful return.
before_page and after_page refer directly to shared_pages. observed_targets
copies lines from that generation's own preceding page, not another candidate.
The original messages and evaluator feedback remain in evidence unchanged.
'''


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def add_chronology(evidence, payload):
    """Add a factual timeline without altering page selection or original fields.

The caller must have verified the base quotes candidate against its audit. This
function independently binds every non-page value and reference to the source;
it does not qualify the lossy excerpts or authorize a Teacher call.
"""
    _require(payload.get('version') == QUOTES_VERSION
             and set(payload) == {'version', 'lossy', 'reversible', 'shared_pages', 'evidence'},
             'An unchanged quotes candidate is required')
    converted, records, _, _ = _discover(evidence)
    _require(payload['evidence'] == converted, 'Source attempts or references changed')
    expanded = {row['page_id']: row['expanded'] for row in records}
    pages = {row['page_id']: row['text'] for row in payload['shared_pages']}
    _require(len(pages) == len(payload['shared_pages']) and set(pages) == set(expanded),
             'Shared page identities changed')
    candidates = []
    bindings = []
    for i, attempt in enumerate(converted['attempts']):
        messages = attempt['trajectory']
        generations = []

        def observation(j):
            if not 0 <= j < len(messages):
                return {}
            message = messages[j]
            body = message.get('content')
            if message.get('role') != 'user':
                return {}
            if isinstance(body, str):
                try:
                    body = json.loads(body, object_pairs_hook=_unique_object)
                except ValueError:
                    return {}
            return body if isinstance(body, dict) else {}

        def page(body):
            for key in PAGE_FIELDS:
                value = body.get(key)
                if isinstance(value, dict) and set(value) == {'page_ref'}:
                    _require(value['page_ref'] in pages, 'Unknown source page')
                    return value['page_ref']
            return None

        for j, message in enumerate(messages):
            if message['role'] != 'assistant':
                continue
            present = 'action_payload' in message
            action = message.get('action_payload')
            _require(action is None or isinstance(action, str), 'Unsupported action payload type')
            before, after = observation(j - 1), observation(j + 1)
            before_page, after_page = page(before), page(after)
            targets = []
            target_status = 'no_nonempty_action_recorded'
            if isinstance(action, str) and action:
                target_status = 'no_preceding_page'
                if before_page is not None:
                    try:
                        targets = observed_targets(action, {'axtree_txt': expanded[before_page]})
                        target_status = 'parsed_from_preceding_page'
                    except (ValueError, SyntaxError, TypeError, AttributeError):
                        target_status = 'action_target_parse_unavailable'
                    retained = {line.strip() for line in pages[before_page].splitlines()}
                    _require(all(target['observed_node'] in retained for target in targets),
                             'A referenced actual target is absent from the candidate')
            row = dict(generation_index=len(generations), message_index=j,
                       action_payload=action,
                       action_record=('payload_field_missing' if not present else
                           'nonempty_action_recorded' if action else 'no_nonempty_action_recorded'),
                       before_page=before_page, after_page=after_page,
                       observed_targets=targets, target_extraction=target_status,
                       following_error_fields={key: deepcopy(after[key]) for key in
                           ('last_action_error', 'action_execution_error') if key in after})
            generations.append(row)
            bindings.append(dict(candidate_index=i, message_index=j,
                source_message_sha256=digest(evidence['attempts'][i]['trajectory'][j]),
                before_message_index=j - 1 if before else None,
                after_message_index=j + 1 if after else None))
        candidates.append(dict(candidate_index=i, generations=generations))
    # Chronology comes first, so long shared pages cannot obscure its boundaries.
    result = dict(chronology_version=VERSION, chronology=candidates, **deepcopy(payload))
    audit = dict(version=VERSION, source_sha256=digest(evidence),
                 base_payload_sha256=digest(payload), payload_sha256=digest(result),
                 generation_bindings=bindings, base_payload_unchanged=True,
                 feedback_used=False, action_success_inferred=False,
                 production_admitted=False, comprehension_validated=False)
    return result, audit
