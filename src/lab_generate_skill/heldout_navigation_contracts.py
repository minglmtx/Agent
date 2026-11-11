"""Explicit test navigation definitions; no live acceptance is inferred.

Only literal page-navigation goals are included. Queries, writes, document
comprehension, and tasks requiring collection contents need separate contracts.
These private bindings must not be serialized wholesale into model input.
"""
import re
from .heldout_initial_state import fingerprint

# Original public wording is pinned as well as identity. These are candidate
# target routes, whose native availability must still be demonstrated.
TARGETS = {
    '2add1a099993117c840c': ('reddit', 'Go to the submit page to create a new post.', '/submit', '^Create submission$', 'submission_form'),
    'aecd0c9e53b704c32388': ('reddit', 'View your profile settings.', '/user/MarvelsGrantMan136/account', '^Editing user(?: settings for)? MarvelsGrantMan136$', 'settings_form'),
    '0e921376a44c2ec752b5': ('reddit', 'Navigate to the worldnews forum', '/f/worldnews', r'^(?:/f/)?worldnews$', 'forum'),
    'fc96b2bd3452a3f77077': ('reddit', 'Go to the Art forum.', '/f/Art', r'^(?:/f/)?Art$', 'forum'),
    '90212aad85003d99d7b5': ('reddit', 'Browse the forums section', '/forums', '^List of forums$', 'forum_directory'),
    '8854cbfdd0ad3ce3e816': ('reddit', 'Navigate to the Home page', '/', '^Featured forums$', 'homepage'),
    '29efdd9aa7e14813a677': ('reddit', 'Navigate to the AskReddit forum to view posts and discussions.', '/f/AskReddit', r'^(?:/f/)?AskReddit$', 'forum'),
    'fddf8c2023b71414f935': ('reddit', 'Browse the AskReddit forum to see discussion questions.', '/f/AskReddit', r'^(?:/f/)?AskReddit$', 'forum'),
    'b0fe1cd04aacadf1b2c6': ('reddit', 'View your user profile page', '/user/MarvelsGrantMan136', '^MarvelsGrantMan136$', 'own_profile'),
    '484a0fb7501756379ca9': ('reddit', 'View all comments across the site.', '/comments', '^Recent comments$', 'comment_directory'),
    'c08a00d56f306b22aa91': ('reddit', 'View all forums in alphabetical order', '/forums/all', '^All forums$', 'alphabetical_forum_directory'),
    '4bc715b66b7ac21c631c': ('map', 'Access the Help page for assistance', '/help', '^Getting Help$', 'information'),
    'b7854974fc544884cce9': ('map', 'Navigate to the Help page.', '/help', '^Getting Help$', 'information'),
    '76af021ae002bccffa1c': ('map', 'View the Copyright information', '/copyright', '^Copyright and License$', 'information'),
    'bfc879e7348e8ec7e436': ('map', 'View copyright information for OpenStreetMap.', '/copyright', '^Copyright and License$', 'information'),
    'bcd599fff64480434db1': ('map', 'Navigate to the About page to learn more about the OpenStreetMap project.', '/about',
                           '^OpenStreetMap provides map data for thousands of websites, mobile apps, and hardware devices$', 'information'),
    'f83a43b283aacf5d3bef': ('map', 'Explore OpenStreetMap Communities.', '/communities', '^Communities$', 'information'),
    '0886bcbb8c65547dd1c4': ('shopping', 'Browse Video Games', '/video-games.html', '^Video Games(?: Items .*)?$', 'category'),
    '29cefa83827eab7bd9c1': ('shopping', 'Explore Grocery & Gourmet Food products.', '/grocery-gourmet-food.html', '^Grocery & Gourmet Food(?: Items .*)?$', 'category'),
    '4a671de68cfac7a7038e': ('shopping', 'Browse the Home & Kitchen category to find household items.', '/home-kitchen.html', '^Home & Kitchen(?: Items .*)?$', 'category'),
}


def candidate(row):
    sid = row['source_task_id']
    target = TARGETS.get(sid)
    if target is None:
        return None
    domain, goal, path, heading, family = target
    if row.get('split') != 'test' or (row['domain'], row['goal']) != (domain, goal):
        raise ValueError('Exact heldout identity, domain and public goal required')
    if row.get('provenance_status') != 'first_frame_bound' or row.get('blockers'):
        raise ValueError('Unblocked original first frame required')
    start = row.get('start_path')
    if not isinstance(start, str) or not start.startswith('/') or start.startswith('//'):
        raise ValueError('Original local start path required')
    completion = dict(path_regex=re.escape(path.rstrip('/')) + '/?' if path != '/' else '/',
                      heading_regex=heading)
    if domain == 'reddit' and family == 'homepage':
        completion['title_regex'] = '^Postmill$'
    wrong = '/forums' if domain == 'reddit' else '/help' if domain == 'map' else '/home-kitchen.html'
    if wrong == path:
        wrong = '/f/worldnews' if domain == 'reddit' else '/copyright' if domain == 'map' else '/video-games.html'
    result = dict(task_id=sid, source_task_id=sid, split='test', domain=domain, goal=goal,
                  start_path=start, task_text_changed=False,
                  baseline_fingerprint=row['baseline_fingerprint'],
                  selected_trace_id=row['selected_trace_id'],
                  initial_observation_sha256=row['initial_observation_sha256'],
                  completion=completion, control_target_path=path, wrong_target_path=wrong,
                  verify_url_only=True, binding_family='heldout_' + family,
                  heldout_quarantine=True, eligible_for_training=False,
                  purpose='codebase_acceptance', formal_test_metric=False,
                  status='draft_requires_native_initialization_controls_and_reset',
                  completion_scope='The requested native page is displayed; no comprehension or query-answer claim.',
                  pending=['native_target_and_page_identity', 'original_initial_state_equivalence',
                           'positive_wrong_object_url_only_404_login_controls', 'two_isolated_reset_cycles',
                           'actual_public_request_isolation', 'actual_actor_execution', 'independent_review'])
    if family in ('category', 'forum', 'forum_directory', 'comment_directory', 'alphabetical_forum_directory'):
        result['pending'].append('native_listing_content_and_blank_listing_negative')
    if family == 'alphabetical_forum_directory':
        result['pending'].append('complete_native_forum_set_and_alphabetical_order')
        result['native_content_profile'] = 'reddit-alphabetical-forum-directory-v1'
    if family == 'forum_directory':
        result['native_content_profile'] = 'reddit-browse-forum-directory-v1'
        # The public task permits every native directory sort and pagination.
        # A private positive-control route must not narrow Actor completion.
        completion['path_regex'] = r'/forums(?:/all|(?:/by_(?:name|title|creation_date|submissions|subscribers))?(?:/[1-9][0-9]*)?)?/?'
        completion['heading_regex'] = '^(?:List of forums|All forums)$'
        result['control_positive_paths'] = ['/forums/all', '/forums/by_name', '/forums/by_title',
            '/forums/by_creation_date', '/forums/by_submissions', '/forums/by_subscribers', '/forums/by_submissions/2']
    if family == 'own_profile':
        result['pending'].append('native_authenticated_profile_identity_and_wrong_user_negative')
    if family in ('submission_form', 'settings_form'):
        result['native_content_profile'] = 'reddit-native-visible-form-v1'
        if family == 'submission_form':
            alternatives = {path: dict(fields=['submission[title]', 'submission[body]'], submit_text='Create submission')}
            # The fixed first frame is already on /submit. A valid untouched
            # form can satisfy this navigation goal; publication is not asked.
            result['allow_initial_success'] = start.rstrip('/') == path
        else:
            prefix = '/user/MarvelsGrantMan136/'
            alternatives = {prefix+'account': dict(fields=['user[username]', 'user[email]'], submit_text='Save changes'),
                            prefix+'preferences': dict(fields=['user_settings[timezone]', 'user_settings[locale]'], submit_text='Save changes')}
            completion['path_regex'] = r'/user/MarvelsGrantMan136/(?:account|preferences)/?'
            result['control_positive_paths'] = [prefix+'preferences']
        completion['heldout_visible_forms'] = alternatives
        result['pending'].append('native_visible_form_and_each_alternative_negative_controls')
    if domain == 'reddit':
        auth = row.get('source_authentication', {})
        if (auth.get('mode') not in ('anonymous', 'authenticated')
                or auth.get('selected_trace_id') != row['selected_trace_id']
                or auth.get('observation_sha256') != row['initial_observation_sha256']):
            raise ValueError('Original header authentication must be bound before native controls')
        result['source_authentication'] = auth
    if sid == '0e921376a44c2ec752b5':
        if start != '/wiki' or result['source_authentication']['mode'] != 'anonymous':
            raise ValueError('The selected original missing-Wiki start changed')
        result['initial_page_policy'] = dict(kind='native_missing_resource', path='/wiki',
                                             required_link_path='/forums')
        result['pending'].append('original_missing_wiki_and_native_forums_recovery_link')
    result['engineering_contract_sha256'] = fingerprint(result)
    return result


def public_task(contract):
    """Allowlist for future request serialization; never include private targets."""
    if (contract.get('split') != 'test' or contract.get('heldout_quarantine') is not True
            or contract.get('eligible_for_training') is not False):
        raise ValueError('Explicit isolated test contract required')
    return {k: contract[k] for k in ('task_id', 'domain', 'goal', 'start_path')}
