"""Private heldout answer evidence; preserve the ordinary Actor protocol.

The ordinary Actor keeps its public goal and free-text finish protocol. Native
identities/prices are evidence only. Unsupported free prose is retained for
content review, never reduced to whichever recognized items happen to pass.
"""
import ast
import json
import re
from urllib.parse import urlsplit

from .heldout_shopping_price_filter import (
    SID, bind_source, digest, judge, public_task, require,
)


def actor_public_task(contract):
    return public_task(bind_source(contract))


def request_review(public, trace, generations, steps):
    # Reuse the existing package replay, identical to the validated Shopping
    # replay. It reconstructs actual requests from public task/browser/actions.
    from .heldout_preferences_requests import replay_requests
    require(public['task_id'] == SID, 'Wrong source')
    return replay_requests(public, trace, generations, steps, answer_fields=None)


def terminal_answer(trace):
    """Read only the last executed finish; request_review must run first."""
    responses = [m for m in trace['messages'] if m['role'] == 'assistant']
    require(responses, 'No actual Actor response')
    action = responses[-1].get('action_payload')
    if not isinstance(action, str):
        return None
    tree = ast.parse(action, mode='eval').body
    if not (isinstance(tree, ast.Call) and isinstance(tree.func, ast.Name)
            and tree.func.id == 'send_msg_to_user' and len(tree.args) == 1
            and not tree.keywords):
        return None
    value = ast.literal_eval(tree.args[0])
    require(isinstance(value, str), 'Executed answer message is not text')
    try:
        envelope = json.loads(value)
    except ValueError:
        return value
    if isinstance(envelope, dict) and set(envelope) == {'value'}:
        answer = envelope['value']
        return answer if isinstance(answer, str) else None
    # No private product IDs or task-specific answer schema is accepted.
    return None


def observed_objects(trace, generations, steps, snapshots):
    """Bind private page snapshots to browser steps actually sent to Actor."""
    require(len(snapshots) == len(steps), 'Every actual browser step needs a private snapshot')
    for index, (step, snapshot) in enumerate(zip(steps, snapshots)):
        require(snapshot['step'] == index == step['step']
                and snapshot['observation_sha256'] == digest(step['observation'])
                and snapshot['state']['url'] == step['observation']['url'],
                'Private snapshot/browser observation pairing differs')
    objects = []; step_index = 0
    for index, generation in enumerate(generations):
        observation = json.loads(trace['messages'][2 * index]['content'])
        state = snapshots[step_index]['state']
        require(state['url'] == observation['url'], 'Observed page URL differs')
        # A name and price visible only in the DOM must not become Actor memory.
        # Check the exact serialized AX supplied in this actual generation.
        ax = observation['axtree_txt']
        for card in state['cards']:
            if card['name'] in ax and card['price_text'] in ax:
                objects.append(dict(product_id=int(card['id']), step=step_index,
                    generation=index, name=card['name'], url=card['url'],
                    snapshot_sha256=digest(snapshots[step_index])))
        if trace['messages'][2 * index + 1].get('action_payload') is not None:
            step_index += 1
    return objects


def resolve_answer(text, objects):
    """Recognize complete explicit name/URL lists; never scrape a good subset.

    This is deliberately a limited parser, not a semantic free-prose judge.
    Other answer forms retain raw text and receive an evidence-gap status.
    """
    require(isinstance(text, str) and text.strip(), 'No textual answer')
    def candidates(item):
        # Markdown emphasis is presentation; names and URLs remain exact.
        if item.startswith('**') and item.endswith('**'):
            item = item[2:-2]
        link = re.fullmatch(r'\[([^\[\]]+)\]\(([^()]+)\)', item)
        matches = []
        for obj in objects:
            identity = (item == obj['name'] or item == obj['url']
                        or item == urlsplit(obj['url']).path)
            if link:
                identity = (link[1] == obj['name'] and link[2] in
                            (obj['url'], urlsplit(obj['url']).path))
            if identity:
                matches.append(obj)
        return matches
    text = text.strip()
    # Product names may contain semicolons or newlines. Match the full name first.
    parts = [text] if candidates(text) else text.splitlines()
    if len(parts) == 1 and not candidates(parts[0]):
        parts = text.split(';')
    selected = []; unresolved = []
    for line in parts:
        item = re.sub(r'^(?:[-*]\s+|[0-9]+[.)]\s+)', '', line.strip())
        if not item:
            unresolved.append(dict(text=item, reason='empty_list_item'))
            continue
        matches = candidates(item)
        if not matches or len({m['product_id'] for m in matches}) != 1:
            unresolved.append(dict(text=item, reason='unobserved_or_unparsed' if not matches else 'ambiguous_identity'))
            continue
        # Latest actual observation is a provenance choice, never a price filter.
        selected.append(max(matches, key=lambda m: (m['generation'], m['step'])))
    return dict(selected=selected, unresolved=unresolved, complete=bool(selected) and not unresolved)


def judge_actual_answer(contract, trace, generations, steps, snapshots, reference):
    """Return answer-branch evidence; current-view evidence is scored separately."""
    binding = bind_source(contract); public = public_task(binding)
    proof = request_review(public, trace, generations, steps)
    raw_answer = terminal_answer(trace)
    result = dict(source_task_id=SID, branch='answer', actual_request_review=proof,
                  raw_answer=raw_answer, selected_objects=[], judgments=[], status='unknown')
    try:
        objects = observed_objects(trace, generations, steps, snapshots)
        resolution = resolve_answer(raw_answer, objects)
        selected = resolution['selected']
        result['selected_objects'] = selected
        result['answer_resolution'] = resolution
    except (ValueError, KeyError, TypeError) as exc:
        result['reason'] = str(exc)
        result['requires_content_review'] = True
        return result
    judgments = [judge(binding, snapshots[o['step']]['state'], reference,
                       branch='answer', identified_ids=[o['product_id']]) for o in selected]
    result['judgments'] = judgments
    statuses = {j['status'] for j in judgments}
    # An identified wrong-price/category object is a valid failure even if a
    # different identified object's evidence is unknown. Never filter bad items.
    result['status'] = ('failure' if 'failure' in statuses else
                        'unknown' if 'unknown' in statuses or not resolution['complete'] else 'success')
    result['requires_content_review'] = result['status'] == 'unknown'
    return result


def aggregate_completion(answer, view, *, protection_status):
    """Keep task evidence separate from unresolved protected-state changes.

    The caller authenticates the request, source and complete required protection
    scope first. ``verified_unchanged`` is not justified by a selected subset or
    by equal account fields alone. This helper does not attribute mutations to
    Actor actions; changed or unverified protection always remains unknown.
    """
    states = {'success', 'failure', 'unknown'}
    require(answer.get('status') in states and view.get('status') in states,
            'Explicit answer/view evidence status required')
    require('raw_answer' in answer, 'Actual terminal answer presence required')
    require(protection_status in {'verified_unchanged', 'changed_unattributed', 'unverified'},
            'Explicit verified or unresolved protection status required')
    task_status = (
        'failure' if answer['status'] == 'failure' else
        'success' if 'success' in (answer['status'], view['status']) else
        'failure' if answer['raw_answer'] is None and view['status'] == 'failure' else
        'unknown'
    )
    status = task_status if protection_status == 'verified_unchanged' else 'unknown'
    reason = (
        'unattributed_protected_state_change' if protection_status == 'changed_unattributed' else
        'protection_evidence_unverified' if protection_status == 'unverified' else
        None
    )
    return dict(source_task_id=SID, status=status,
                reward=None if status == 'unknown' else float(status == 'success'),
                task_status_without_protection=task_status,
                protection_status=protection_status, reason=reason,
                answer_judgment=answer, view_judgment=view,
                actor_admission=False, eligible_for_training=False)


def verify_execution_binding(packet_ref, plan_ref, job_id, claim, launch, execution, result):
    """Check source/attempt/closure linkage before admitting any Actor result.

    The outer reviewer must first verify all referenced files and closed archive
    bytes using the reused launcher/archive reader. These are parsed records,
    not a substitute for that byte-level independent review.
    """
    require(claim['packet'] == packet_ref and claim['source_task_id'] == SID
            and claim['job_id'] == job_id and claim['automatic_retry'] is False,
            'Persistent source claim differs')
    require(launch['source_task_id'] == SID and launch['packet'] == packet_ref
            and launch['plan'] == plan_ref and launch['job_id'] == job_id
            and launch['claim'] == claim, 'Actual prelaunch claim binding differs')
    require(execution['source_task_id'] == SID and execution['plan'] == plan_ref
            and execution['job_id'] == job_id and execution['launch'] == launch
            and execution['process_quiescence_confirmed'] is True
            and execution['closed_archive_verified'] is True,
            'Actual execution/closed archive binding missing')
    require(result['source_task_id'] == SID and result['packet'] == packet_ref
            and result['job_id'] == job_id and result['execution_status'] == 'completed'
            and result['service_processes_closed'] is True
            and result['temporary_state_removed'] is True
            and result['eligible_for_training'] is False,
            'Actual task completion/cleanup binding missing')
    return dict(source_claim_bound=True, actual_job_id=job_id,
                closure_required_and_bound=True, automatic_retry=False)
