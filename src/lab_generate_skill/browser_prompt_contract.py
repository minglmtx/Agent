"""Shared observation and response contracts; contains no evaluator answers."""
import json
import os
from collections.abc import Mapping

VIEWPORT_GUIDANCE = """Observation scope: the accessibility tree contains the current viewport, not the whole page.
If information needed for the goal is not visible, scroll the page or expand the relevant
section and inspect the new observation. Do not infer absence, zero, or completion from
an unseen field, and do not substitute a related field for the requested one. If all
necessary information is already visible, no extra scrolling is needed. Resolve element
IDs from the current observation after scrolling, expanding, or navigating."""
SKILL_GUIDANCE = """Skills are textual strategy guidance, not callable tools. A skill title or a
function-like name in a skill is never an additional operation. Translate the guidance
into the allowed browser operations using controls in the current observation."""
ANSWER_VALUES_GUIDANCE = (
    'Return the requested field values without adding surrounding field labels or explanatory prefixes. '
    'When a field explicitly requests a UI label, preserve that observed label as its value.'
)


def viewport_enabled():
    policy = os.environ.get('ADMIN_AX_POLICY', 'viewport-v1')
    if policy not in ('viewport-v1', 'full'):
        raise ValueError('Unknown ADMIN_AX_POLICY: '+policy)
    return policy == 'viewport-v1'


def query_answer_example(fields):
    # Placeholders describe output types; never derive examples from references.
    if isinstance(fields, Mapping):
        # Typed site queries may call a collection "projects", "directories",
        # or any other name. The public type, not the spelling, defines its shape.
        examples = {'record_set': [], 'record_subset': [], 'text_list': [], 'number': 0.0,
                    'decimal': 0.0, 'integer': 0, 'boolean': False}
        return {k: examples.get(kind, '<observed value>') for k, kind in fields.items()}
    # Legacy Admin callers provide field names without a type mapping.
    return {k: ([] if k in ('items', 'excluded_websites') else '<observed value>') for k in fields}


def query_finish_instruction(fields, *, record_fields=(), entity=None):
    example = json.dumps({'action':'finish', 'answer':query_answer_example(fields)})
    rules = [
        ANSWER_VALUES_GUIDANCE,
        'The <observed value> examples are placeholders; use the exact scalar types required by the public task schema.',
        'All example values, including 0, 0.0, false and [], illustrate types only; replace them with observed answers.',
        'Boolean fields must be JSON true or false, not quoted strings, numeric status codes or explanatory text.',
        'Money and numeric fields must follow the public schema; numeric strings are permitted only when that schema permits strings. Use no currency symbols or thousands separators, and no units.',
        'For string fields, preserve the requested text and any units explicitly required by the field definition.',
        'Telephone values must omit the T: or Tel: label; retain the phone number itself.',
        'Record identifiers are exact strings: preserve all leading zeros; do not convert an ID to a number.',
        'List-valued fields must be JSON arrays; use [] for no results, never an empty string, null or the word None.'
    ]
    names = set(fields) | set(record_fields)
    if 'is_active' in names:
        rules.append('is_active uses the documented status code: Enabled = 1, Disabled = 0. Return the code, not the label.')
    if 'excluded_websites' in names:
        rules.append('excluded_websites is an array of website-name strings, including [] if no websites are selected.')
    if 'items' in names and (not isinstance(fields, Mapping)
                            or fields.get('items') in ('record_set', 'record_subset')):
        rules.append('items is an array of record objects, not a string. [] means the matching set is empty.')
    return ('To finish this query, output '+example+'. Put exactly these requested fields '
            'inside answer: '+', '.join(fields)+'. Do not return bare fields or a serialized JSON string. '
            + ' '.join(rules))


FULL_AX_GUIDANCE = """Observation scope: the accessibility tree covers the current page without viewport
filtering. It may include off-screen elements, but not future pages or content not yet
loaded. Read the requested field directly; do not substitute a related field. Expand
relevant sections or navigate when information is unavailable. Resolve element IDs from
the current observation and use browser feedback to recover from interaction errors."""
