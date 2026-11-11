"""Opt-in public interaction memory; raw evidence is distinct from prompt views.

Six executed browser calls retain their issued observations and public returns.
Parse failures are separate generations. Earlier events describe attempts, never
inferred intent, task success or database persistence. No evaluator is accepted.
"""
import copy
import hashlib
import json

from .action_history import observed_targets
from .adaptive_observation import select_actor_observation
from .observation_budget import ObservationBudgetError
from .public_read_memory import MEMORY_MARKER, PublicReadProtocol

VERSION = 'actor-public-six-exchanges-v1'


def memory_for_policy(policy):
    """Explicit candidate selection shared by source execution and its review."""
    if policy is None:
        return None
    if policy != 'related_public_quotes_v1':
        raise ValueError('Unqualified Actor memory policy')
    return ActorEventMemory(maximum_tokens=16384, maximum_early_events=32,
                            history_page_policy=policy)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class ActorMemoryBudgetError(ObservationBudgetError):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__('Six interactions and current observation exceed the explicit Actor input budget')


class ActorEventMemory:
    def __init__(self, *, maximum_tokens=16384, maximum_early_events=32,
                 history_page_policy='full_issued_pages'):
        if type(maximum_tokens) is not int or maximum_tokens < 1:
            raise ValueError('Positive input-token budget required')
        if type(maximum_early_events) is not int or maximum_early_events < 0:
            raise ValueError('Nonnegative early-event bound required')
        if history_page_policy not in ('full_issued_pages', 'related_public_quotes_v1'):
            raise ValueError('Unknown historical observation policy')
        self.maximum_tokens = maximum_tokens
        self.maximum_early_events = maximum_early_events
        self.history_page_policy = history_page_policy
        self.start('unstarted')

    def start(self, trace_id):
        self.trace_id = trace_id
        self.exchanges = []
        self.pages = {}
        self.requests = []
        self.parse_failures = []
        self.last_budget = None
        self.backend_budget = None
        self._prepared = None
        self._issued = None
        self._view_audit = {}

    def validate_backend_budget(self, backend):
        """Configured input limits must contain the complete preflighted request.

        Existing inference counters include their actual chat template. Their
        wrappers expose the underlying backend through delegate or backend.
        A message acknowledgement alone cannot detect tokenizer truncation.
        """
        current, seen, limits = backend, set(), []
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            settings = getattr(current, 'settings', None)
            limit = getattr(settings, 'max_input_tokens', None)
            if type(limit) is int and limit > 0:
                limits.append(limit)
            current = getattr(current, 'delegate', None) or getattr(current, 'backend', None)
        if not limits or self.maximum_tokens > min(limits):
            raise ValueError('Memory input budget must fit the explicit underlying backend input limit')
        self.backend_budget = dict(memory_input_limit=self.maximum_tokens,
                                   configured_backend_input_limit=min(limits))

    @staticmethod
    def page(body):
        text = body['observation']
        # Reuse PublicReadMemory in the current observation; do not copy its
        # accumulated record collection into every historical page as well.
        parts = text.rsplit('\n\n' + MEMORY_MARKER, 1)
        fields = ('url', 'observation_scope', 'observation_mode', 'observation_policy',
                  'open_tabs', 'active_tab_index', 'available_files', 'downloads',
                  'download_feedback', 'printed_files', 'print_feedback',
                  'record_sections', 'page_wait')
        result = {key: copy.deepcopy(body[key]) for key in fields if key in body}
        result['observation'] = parts[0]
        if len(parts) == 2:
            result['embedded_read_memory_omitted'] = True
        return result

    def _earlier_events(self):
        events = []
        for item in self.exchanges[:-6]:
            event = {k: copy.deepcopy(item[k]) for k in
                     ('action', 'targets', 'status', 'url_before', 'url_after', 'error') if k in item}
            event.update(historical=True, occurrences=1,
                         first_step=item['step'], last_step=item['step'])
            # Same bid text is insufficient. Merge only adjacent calls with the
            # same publicly observed target, result and issued page identities.
            identity = digest([event['action'], event.get('targets'), event['status'],
                               event.get('url_before'), event.get('url_after'), event.get('error'),
                               item['before_page'], item.get('after_page')])
            if event.get('targets') and events and events[-1]['_identity'] == identity:
                events[-1]['occurrences'] += 1
                events[-1]['last_step'] = item['step']
            else:
                event['_identity'] = identity
                events.append(event)
        return [{k: v for k, v in item.items() if k != '_identity'} for item in events]

    def _messages(self, protocol, goal, obs, history, action_description, skills, early_count):
        messages = copy.deepcopy(protocol.messages(goal, obs, history,
                                    action_description=action_description, skills=skills))
        body = json.loads(messages[-1]['content'])
        if not isinstance(body.get('observation'), str):
            raise ValueError('Structured Actor observation required')
        for key in ('previous_actions', 'action_counts', 'history_length'):
            body.pop(key, None)
        # Preserve the actual public tool feedback, including click interceptors.
        body['last_action_error'] = obs.get('last_action_error', '')
        current = self.page(body)
        current_key = digest(current)
        recent, pages = [], {}
        for source in self.exchanges[-6:]:
            item = {k: copy.deepcopy(v) for k, v in source.items()
                    if k not in ('source', 'after_source', 'before_page', 'after_page')}
            for side in ('before_page', 'after_page'):
                key = source.get(side)
                if key is None:
                    # This return is the current observation about to be sent.
                    item[side] = 'current_observation' if side == 'after_page' and source is self.exchanges[-1] else None
                elif key == current_key:
                    item[side] = 'current_observation'
                else:
                    label = 'page_' + key[:16]
                    if label in pages and pages[label] != self.pages[key]:
                        raise ValueError('Historical page label collision')
                    pages[label] = self.pages[key]
                    item[side] = label
            item['state'] = 'historical_observation_not_current_state'
            recent.append(item)
        earlier = self._earlier_events()
        self._view_audit = {}
        if self.history_page_policy == 'related_public_quotes_v1':
            from .actor_history_quotes import related_quotes
            for label in list(pages):
                keys = [key for key in self.pages if 'page_' + key[:16] == label]
                if len(keys) != 1:
                    raise ValueError('Historical quote source is ambiguous')
                key = keys[0]
                targets, previous = [], []
                for source in self.exchanges[-6:]:
                    if source['before_page'] == key:
                        targets.extend(source['targets'])
                    if source.get('after_page') == key and source['before_page'] != key:
                        previous.append(self.pages[source['before_page']])
                pages[label], audit = related_quotes(pages[label], targets=targets, previous_pages=previous)
                self._view_audit[label] = dict(source_page_sha256=key, **audit)
        selected = earlier[-early_count:] if early_count else []
        recent_failures = self.parse_failures[-6:]
        body['working_memory'] = dict(version=VERSION, recent_interactions=recent,
            historical_pages=pages, earlier_events=selected,
            generation_errors=[{k: v for k, v in row.items() if k != 'source'} for row in recent_failures],
            omitted_earlier_event_groups=len(earlier) - len(selected),
            omitted_earlier_generation_errors=len(self.parse_failures) - len(recent_failures),
            complete_recent_browser_interactions=len(recent),
            history_page_policy=self.history_page_policy,
            current_element_ids_only=True, task_success_asserted=False)
        messages[0]['content'] += (
            '\nWorking memory describes earlier attempts and public feedback. '
            'A returned click is not proof of saving or persistence. Historical pages '
            'and element IDs are past evidence; use only the current observation for '
            'element operations. current_observation refers to this request. Earlier omissions are explicit.\n')
        messages[0]['content'] += ('Historical page references contain complete previously issued page text.\n'
            if self.history_page_policy == 'full_issued_pages' else
            'Historical page references contain selected verbatim public lines. These lossy excerpts '
            'declare omitted lines and are not complete observations or current state.\n')
        messages[-1]['content'] = json.dumps(body, ensure_ascii=False)
        return messages

    def prepare(self, protocol, goal, obs, history, *, token_counter, action_description=None, skills=None):
        if protocol is None or protocol.name != 'structured_observed' or not callable(token_counter):
            raise ValueError('Observed structured protocol and actual token counter required')
        # Refresh the one acknowledged read store, but select the observation
        # only once with the complete memory request. A preliminary selection
        # would replace the real viewport and corrupt the later fallback.
        if isinstance(protocol, PublicReadProtocol):
            obs = protocol.refresh(obs)
        def build(view, count=0):
            return self._messages(protocol, goal, view, history, action_description, skills, count)
        if protocol.observation_policy == 'viewport-v1':
            selected = obs
        else:
            selected = select_actor_observation(obs, build, token_counter, self.maximum_tokens,
                compact_rows=protocol.observation_policy == 'full-lossless-rows-if-fits-v2')
        mandatory = build(selected)
        tokens = token_counter(mandatory)
        diagnostic = dict(version=VERSION, mandatory_input_tokens=tokens,
            maximum_input_tokens=self.maximum_tokens, recent_interactions=min(6, len(self.exchanges)),
            recorded_browser_calls=len(self.exchanges), silently_truncated=False)
        if tokens > self.maximum_tokens:
            self.last_budget = dict(diagnostic, status='blocked_mandatory_history_and_observation')
            raise ActorMemoryBudgetError(self.last_budget)
        count = min(self.maximum_early_events, len(self._earlier_events()))
        while True:
            request = build(selected, count)
            actual_tokens = token_counter(request)
            if actual_tokens <= self.maximum_tokens:
                break
            count -= 1
        self.last_budget = dict(diagnostic, status='fits', input_tokens=actual_tokens,
                                included_early_event_groups=count)
        self._prepared = copy.deepcopy(request)
        return selected, request

    def acknowledge(self, generation_index, sent):
        if not isinstance(sent, list) or sent != self._prepared:
            raise ValueError('Memory requires the exact budgeted request actually issued by the backend')
        body = json.loads(sent[-1]['content'])
        page = self.page(body)
        key = digest(page)
        self.pages[key] = copy.deepcopy(page)
        source = dict(trace_id=self.trace_id, generation_index=generation_index,
                      request_sha256=digest(sent), page_sha256=key)
        self.requests.append(dict(source=source, budget=copy.deepcopy(self.last_budget),
                                  historical_page_selections=copy.deepcopy(self._view_audit),
                                  public_read_memory_present=MEMORY_MARKER in body['observation']))
        if self.exchanges and self.exchanges[-1].get('after_page') is None:
            previous = self.exchanges[-1]
            previous.update(after_page=key, after_source=copy.deepcopy(source))
        self._issued = dict(source=source, body=copy.deepcopy(body), page=key)

    def invalid_generation(self, generation_index, error, kind):
        if not self._issued or self._issued['source']['generation_index'] != generation_index:
            raise ValueError('Parse failure has no matching issued request')
        self.parse_failures.append(dict(generation_index=generation_index,
            executed=False, error=error, kind=kind, source=copy.deepcopy(self._issued['source'])))

    def action_started(self, generation_index, action, observation):
        if not self._issued or self._issued['source']['generation_index'] != generation_index:
            raise ValueError('Action has no matching issued request')
        if (observation.get('observation_mode') == 'full'
                and observation.get('observation_policy') == 'full-lossless-rows-if-fits-v2'):
            from .actor_history_quotes import page_text
            observation = dict(observation, axtree_txt=page_text(self.page(self._issued['body'])))
        self.exchanges.append(dict(step=len(self.exchanges), generation_index=generation_index,
            action=action, targets=observed_targets(action, observation), status='return_not_recorded',
            url_before=self._issued['body'].get('url'), before_page=self._issued['page'],
            source=copy.deepcopy(self._issued['source'])))

    def action_returned(self, observation):
        row = self.exchanges[-1]
        error = observation.get('last_action_error', '')
        row.update(status='reported_error' if error else 'returned_without_reported_error',
                   url_after=observation.get('url'), error=error)

    def audit(self):
        return copy.deepcopy(dict(version=VERSION, trace_id=self.trace_id, requests=self.requests,
            history_page_policy=self.history_page_policy,
            exchanges=self.exchanges, issued_pages=self.pages, generation_errors=self.parse_failures,
            last_budget=self.last_budget, backend_budget=self.backend_budget, private_evaluator_input=False,
            terminal_unissued_observation_location='original_trajectory_terminal_observation',
            source_indices_are_internal=True, activation='explicit_caller_argument'))
