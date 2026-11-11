"""Description-task protocol grounded in the installed blank-project form.

A personal-only account has a fixed Project URL, not a namespace selector.
Checking that field is possible in both native layouts. This is a declared
training-task revision; it does not silently reinterpret previous answers.
"""
from copy import deepcopy

OPERATIONS = ['open_project_creation', 'choose_blank_project', 'set_project_name',
              'check_project_namespace', 'choose_visibility', 'submit_create_project']

NAMESPACE_READER = r'''(form) => {
 if(!form)return null;
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const labels=[...form.querySelectorAll('label[for="project_namespace_id"]')].filter(visible);
 if(labels.length!==1)return null;
 const fixed=[...form.querySelectorAll('.static-namespace')].filter(visible);
 const selectors=[...form.querySelectorAll('.js-vue-new-project-url-select')].filter(visible);
 const inputs=[...form.querySelectorAll('[name="project[namespace_id]"]')];
 if(fixed.length===1&&selectors.length===0&&inputs.length===1&&inputs[0].type==='hidden'&&/^[1-9][0-9]*$/.test(inputs[0].value))
   return {label:labels[0].innerText.trim(),mode:'fixed',display:fixed[0].innerText.trim()};
 if(fixed.length===0&&selectors.length===1)
   return {label:labels[0].innerText.trim(),mode:'selectable',display:selectors[0].innerText.trim()};
 return null;
}'''


def revise_contract(contract):
    if contract.get('public_parameters', {}).get('operation') != 'blank_description':
        raise ValueError('Blank project description contract required')
    result = deepcopy(contract)
    goal = ('Inspect the installed GitLab blank-project form, then describe the process '
            'of creating a private blank project as an '
            'ordered JSON steps array using the actual native UI labels. Include checking '
            'the Project URL namespace; it may be fixed for the current account. '
            'Use one object per declared operation, with exactly operation and ui_label '
            'as string fields. Field setup operations may appear in any valid order. '
            'Describe the process without creating a project.')
    result['goal'] = goal
    result['task_text_changed'] = True
    result['goal_revision'] = dict(version='gitlab-blank-description-observed-process-v3',
        original_goal=result['original_goal'], derived_goal=goal,
        reason='Explicitly require native form inspection and record objects; accept '
               'independent field setup in any order while retaining entry and submission dependencies.',
        equivalent_to_original_goal=False)
    result['public_parameters']['operation_vocabulary'] = sorted(OPERATIONS)
    result['public_parameters']['description_format'] = {
        'steps': 'ordered records with operation and ui_label'}
    result['public_task_input'] = dict(goal=goal,
        public_parameters=deepcopy(result['public_parameters']), required_unresolved_public_parameters=[])
    return result


def valid_operation_order(operations):
    """Necessary process dependencies, not a secret total field-edit order.

    Opening creation and choosing blank precede field setup. Submission comes
    last. Name, namespace and visibility are independent form setup steps.
    This validates a description; it never executes the described submission.
    """
    if (not isinstance(operations, list) or len(operations) != len(OPERATIONS)
            or any(not isinstance(op, str) for op in operations)
            or len(set(operations)) != len(OPERATIONS)
            or set(operations) != set(OPERATIONS)):
        return False
    return (operations[:2] == OPERATIONS[:2]
            and operations[-1] == 'submit_create_project')


def namespace_label(form):
    field = form.get('namespace_field')
    if (not isinstance(field, dict) or field.get('mode') not in ('fixed', 'selectable')
            or not isinstance(field.get('label'), str) or not field['label'].strip()
            or not isinstance(field.get('display'), str) or not field['display'].strip()):
        return None
    return field['label'].strip()


def require_complete_labels(labels):
    """A broken positive-control input is a harness error, never a model failure."""
    missing = [operation for operation in OPERATIONS
               if not isinstance(labels.get(operation), str) or not labels[operation].strip()]
    if missing:
        raise ValueError('Native description control labels missing: ' + ', '.join(missing))
    return {'steps': [{'operation': operation, 'ui_label': labels[operation]}
                      for operation in OPERATIONS]}
