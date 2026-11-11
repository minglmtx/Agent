"""Private heldout preferences binding; never grants Actor or training admission.

The ordinary Actor receives actor_task() only. Capture/assessment functions can
be used by a later reviewed native probe and live entry without changing the
original preferences evaluator or its development-only admission guard.
"""
from copy import deepcopy
import hashlib
import json
from urllib.parse import urlsplit
from . import site_preferences_rules as native

VERSION = 'heldout-preferences-source-binding-v1'
IDENTITY = ('source_task_id', 'domain', 'goal', 'start_path',
            'selected_trace_id', 'initial_observation_sha256')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def bind_source(source, comparison, declaration):
    """Declaration is explicitly reviewed metadata, not an inferred answer."""
    require(source.get('split') == 'test' and source.get('domain') == 'reddit'
            and source.get('eligible_for_training') is False, 'Heldout source required')
    require(all(source.get(k) == comparison['source_task'].get(k) == declaration.get(k)
                for k in IDENTITY), 'Original source identity changed')
    require(declaration.get('username') == 'MarvelsGrantMan136', 'Original account required')
    field, target = declaration.get('field'), declaration.get('target')
    require(field in {'auto_fetch_submission_titles', 'timezone'}, 'Unreviewed preference field')
    require((field == 'auto_fetch_submission_titles' and target is False)
            or (field == 'timezone' and target == 'Europe/London'), 'Public target differs')
    require(comparison.get('selected_before_action_only') is True
            and comparison.get('two_cold_signatures_equal') is True, 'Two retained initial captures required')
    captures = comparison.get('native_captures')
    require(isinstance(captures, list) and len(captures) == 2
            and [r['checkpoint']['cycle'] for r in captures] == [0, 1]
            and all(r['checkpoint']['source_task_id'] == source['source_task_id'] for r in captures),
            'Original source/cycle binding required')
    for row in captures:
        auth = row['authentication']
        require(auth == dict(expected='authenticated', account_menu_visible=True,
                             login_signup_visible=False, passed=True), 'Retained account state differs')
        u = urlsplit(row['native_url'])
        require(u.path + ('?' + u.query if u.query else '') == source['start_path'], 'Retained start differs')
    state = declaration.get('initial_state_disposition')
    require(state in {'retained_original_business_match', 'blocked_original_locale_order_difference'},
            'Explicit initial-state disposition required')
    if state == 'retained_original_business_match':
        require(all(not r['source_business_missing_or_changed'] and not r['native_business_extra_or_changed']
                    for r in captures), 'Business differences cannot be normalized away')
    else:
        require(any(r['source_business_missing_or_changed'] or r['native_business_extra_or_changed']
                    for r in captures), 'Blocked initial difference lacks evidence')
    require(captures[0]['signature'] == captures[1]['signature'], 'Retained initial signatures differ')
    c = dict(task_id=source['source_task_id'], source_task_id=source['source_task_id'],
             domain='reddit', goal=source['goal'], start_path=source['start_path'],
             preferences=dict(username=declaration['username'], targets={field: target}),
             heldout_quarantine=True, eligible_for_training=False, split='test')
    value = dict(version=VERSION, source={k: source[k] for k in IDENTITY},
                 contract=c, declaration=deepcopy(declaration),
                 retained_initial_signature=captures[0]['signature'],
                 retained_comparison_sha256=digest(comparison),
                 initial_state_disposition=state, actor_admission=False,
                 evaluation_ready=False, eligible_for_training=False)
    value['binding_sha256'] = digest(value)
    return value


def validate_binding(binding, *, executable=False):
    require(binding.get('version') == VERSION, 'Preferences binding version differs')
    value = deepcopy(binding); expected = value.pop('binding_sha256', None)
    require(digest(value) == expected and binding.get('actor_admission') is False
            and binding.get('evaluation_ready') is False
            and binding.get('eligible_for_training') is False, 'Binding changed or masquerades as admission')
    c, d, s = binding['contract'], binding['declaration'], binding['source']
    require(d.get('username') == 'MarvelsGrantMan136', 'Original account required')
    require((d.get('field') == 'auto_fetch_submission_titles' and d.get('target') is False)
            or (d.get('field') == 'timezone' and d.get('target') == 'Europe/London'),
            'Reviewed target field/type changed')
    require(all(d.get(k) == s[k] for k in IDENTITY)
            and c['task_id'] == c['source_task_id'] == s['source_task_id']
            and c['goal'] == s['goal'] and c['start_path'] == s['start_path']
            and c['domain'] == s['domain'] == 'reddit'
            and c['heldout_quarantine'] is True and c['eligible_for_training'] is False
            and c['split'] == 'test'
            and digest(c['preferences']) == digest(dict(username=d['username'], targets={d['field']: d['target']}))
            and binding['initial_state_disposition'] == d['initial_state_disposition'],
            'Private contract no longer binds the original source')
    if executable:
        require(binding['initial_state_disposition'] == 'retained_original_business_match',
                'Original locale/order initial state is unresolved')
    return c


def actor_task(binding):
    """Public projection, not launch authorization; no route/account answer hints."""
    c = validate_binding(binding, executable=True)
    return dict(task_id=c['task_id'], domain=c['domain'], goal=c['goal'], skills=[])


def require_initial(binding, page, preferences, *, site_origin):
    from .heldout_actor_gate import initial_signature
    c = validate_binding(binding, executable=True)
    require(initial_signature(page, site_origin) == binding['retained_initial_signature'],
            'Actual original block-list initial view differs')
    u, o = urlsplit(page['url']), urlsplit(site_origin)
    require((u.scheme, u.netloc) == (o.scheme, o.netloc)
            and u.path + ('?' + u.query if u.query else '') == c['start_path'], 'Actual initial source route differs')
    require_preferences_state(c, preferences)
    field, target = next(iter(c['preferences']['targets'].items()))
    require(preferences['values'][field] != target, 'Requested preference already satisfied at initial reset')
    return dict(initial_view_equal=True, original_account_bound=True,
                initially_unsatisfied=True, binding_sha256=binding['binding_sha256'])


def require_preferences_state(contract, state):
    require(isinstance(state, dict) and set(state) == {'user_id', 'username', 'values'}
            and type(state['user_id']) is int and state['user_id'] > 0
            and state['username'] == contract['preferences']['username']
            and isinstance(state['values'], dict) and set(state['values']) == set(native.FIELDS),
            'One complete original account preference snapshot required')
    field, target = next(iter(contract['preferences']['targets'].items()))
    require(type(state['values'][field]) is type(target), 'Native preference type differs')
    return state


def evaluate_attempt(binding, terminal_page, before, after, *, site_origin, runtime_error=None):
    """Actual saved native state plus exact whole-user protection; no Actor actions."""
    from .heldout_preferences_protection import verify_transition
    c = validate_binding(binding, executable=True)
    try:
        require_preferences_state(c, before['preferences'])
        require_preferences_state(c, after['preferences'])
        protection = verify_transition(binding, before, after)
        judgment = native.evaluate_preferences(c, terminal_page, before['preferences'],
                                               after['preferences'], site_origin=site_origin,
                                               runtime_error=runtime_error)
        return dict(version=VERSION, binding_sha256=binding['binding_sha256'],
                    protection=protection, native_judgment=judgment,
                    status=judgment['status'], reward=judgment['reward'],
                    evaluation_ready=False, eligible_for_training=False)
    except (ValueError, KeyError, TypeError) as exc:
        return dict(version=VERSION, binding_sha256=binding['binding_sha256'],
                    status='unknown', reward=None, reason=str(exc),
                    evaluation_ready=False, eligible_for_training=False)
