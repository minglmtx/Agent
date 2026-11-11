"""Optional exact sharing of repeated observation metadata in a quotes payload.

This is a derived offline view, with no dispatch or caller activation. Pages,
actions, errors, URLs, feedback and generated text are untouched. The underlying
page excerpts remain lossy; restoring this layer does not restore omitted pages.
"""
from copy import deepcopy

from .teacher_evidence_pages import digest

VERSION = 'teacher-observation-defaults-v1'
FIELDS = ('goal', 'observation_scope', 'open_tabs', 'active_tab_index',
          'observation_mode', 'observation_policy')
KEY = 'shared_observation_metadata'
GUIDE = '''
Each candidate may have shared_observation_metadata. Its exact fields apply to
every object-valued user observation in THAT candidate's trajectory. These fields
were present and identical in all those observations, and are written only once.
Do not apply them to another candidate or to string-valued messages. All other
observation fields are written in their original step. Per-step URLs, recorded actions,
errors, terminal-record sources and feedback are never moved into this metadata.
This layer introduces no page differences or arithmetic. The underlying quoted
pages still have their explicit omissions; sharing metadata restores no missing
page lines and establishes no model-understanding or execution-success claim.
'''


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _observations(attempt):
    _require(isinstance(attempt, dict) and isinstance(attempt.get('trajectory'), list),
             'Candidate trajectory required')
    result = []
    for index, message in enumerate(attempt['trajectory']):
        _require(isinstance(message, dict), 'Invalid trajectory message')
        if message.get('role') == 'user' and isinstance(message.get('content'), dict):
            result.append((index, message['content']))
    return result


def _base(payload):
    _require(isinstance(payload, dict) and isinstance(payload.get('evidence'), dict)
             and isinstance(payload['evidence'].get('attempts'), list),
             'Structured base quotes evidence required')
    _require(payload.get('version') == 'teacher-evidence-verbatim-quotes-v1'
             and payload.get('lossy') is True and payload.get('reversible') is False,
             'Use the verified explicitly lossy quotes base')
    _require('metadata_sharing_version' not in payload, 'Already transformed input')
    for attempt in payload['evidence']['attempts']:
        _require(KEY not in attempt, 'Reserved candidate metadata field already present')
        _observations(attempt)


def pack(base):
    """Share only exact, present-in-every-observation values inside one attempt."""
    _base(base)
    output = deepcopy(base)
    output['metadata_sharing_version'] = VERSION
    records = []
    for index, attempt in enumerate(output['evidence']['attempts']):
        observations = _observations(attempt)
        shared = {}
        if len(observations) > 1:
            for field in FIELDS:
                values = [body[field] for _, body in observations if field in body]
                # Serialized equality preserves JSON types: True must not alias 1.
                if len(values) == len(observations) and len({digest(v) for v in values}) == 1:
                    shared[field] = deepcopy(values[0])
        if shared:
            attempt[KEY] = shared
            for _, body in observations:
                for field in shared:
                    del body[field]
        records.append(dict(candidate_index=index, observation_message_indexes=[i for i, _ in observations],
                            fields=list(shared), shared_sha256=digest(shared),
                            original_attempt_sha256=digest(base['evidence']['attempts'][index])))
    audit = dict(version=VERSION, base_sha256=digest(base), derived_sha256=digest(output),
                 candidates=records, this_layer_reversible=True, underlying_pages_lossy=True,
                 action_or_error_fields_moved=False, production_admitted=False)
    _require(restore(output) == base, 'Metadata sharing changed the base evidence')
    return output, audit


def restore(derived):
    """Restore this exact metadata layer, never reconstruct omitted source pages."""
    _require(isinstance(derived, dict) and derived.get('metadata_sharing_version') == VERSION,
             'Wrong metadata sharing version')
    output = deepcopy(derived)
    del output['metadata_sharing_version']
    _require(isinstance(output.get('evidence'), dict)
             and isinstance(output['evidence'].get('attempts'), list), 'Missing attempts')
    for attempt in output['evidence']['attempts']:
        observations = _observations(attempt)
        shared = attempt.pop(KEY, {})
        _require(isinstance(shared, dict) and set(shared) <= set(FIELDS), 'Unsupported shared fields')
        _require(not shared or len(observations) > 1, 'Shared metadata has no repeated observations')
        for _, body in observations:
            _require(not set(body) & set(shared), 'Ambiguous local/shared observation field')
            body.update(deepcopy(shared))
    _base(output)
    return output


def verify(base, derived, audit):
    expected, expected_audit = pack(base)
    _require(digest(derived) == digest(expected) and digest(audit) == digest(expected_audit),
             'Derived metadata, source bindings or audit changed')
    return True
