"""Optional native editor navigation family; no task-specific actor strategy.

Setup explicitly declares a synthetic local account and native OAuth as part
of a fresh disposable baseline. Subsequent OAuth writes are still tracked.
Readers save only public origin/path and the parsed numeric iframe map triplet.
This family proves navigation, not tile coverage, geographic editing or saving.
"""
import hashlib
import json
import math
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

from .map_community_fixture import VERSION as COMMUNITY_VERSION, USERNAME, PASSWORD, records
from .map_editor_state import checks as state_checks, read_editor_state, navigation_context_changed
from .map_reset_guard import STATE_SQL, checked_state
from .map_view import native_zoom, wait_native_view
from .io_utils import atomic_write_json
from .map_native_account_bootstrap import initialize_native_account

VERSION = 'native-map-editor-navigation-v1'
INITIALIZATION = 'fresh_document_original_start_v2'
NATIVE_FILES = (
    'CONFIGURE.md', 'app/models/user.rb', 'app/views/site/id.html.erb',
    'app/assets/javascripts/edit/id.js.erb',
    'app/assets/javascripts/id.js', 'app/assets/javascripts/index.js',
)
FEEDBACK = {
    'local_editor_page': 'The final page is the local map editing page.',
    'native_editor_frame': 'The native editor frame belongs to the current website.',
    'editor_configured': 'The native editor is configured.',
    'editor_embed_visible': 'The editor is displayed.',
    'editor_map_visible': 'The native editor map is displayed.',
    'native_map_state': 'The editor exposes a valid current map view.',
    'requested_area': 'The editor displays the area from the initial task view.',
}

EDIT_CONTROL = r'''() => {
 const e = document.querySelector('#edit_tab a');
 if (!e) return {present:false};
 const style = getComputedStyle(e);
 return {present:true, href:e.getAttribute('href'),
   visible:!!e.getClientRects().length && style.visibility !== 'hidden' && style.display !== 'none',
   disabled:e.classList.contains('disabled') || e.getAttribute('aria-disabled') === 'true',
   pointer_events:style.pointerEvents};
}'''


def hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def origin(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username is not None or p.password is not None:
        raise ValueError('Explicit local website origin required')
    return p.scheme, p.hostname.lower(), p.port or (80 if p.scheme == 'http' else 443)


def local_path(path):
    if not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or '\\' in path:
        raise ValueError('Original local task path required')
    p = urlsplit(path)
    if p.scheme or p.netloc:
        raise ValueError('Task start must be a local path')
    return path


def native_edit_url(site_origin, observed_href):
    """Only a privately observed same-origin native link may drive a control."""
    if not isinstance(observed_href, str) or not observed_href or '\\' in observed_href:
        raise ValueError('Native Edit href missing')
    result = urljoin(site_origin.rstrip('/') + '/', observed_href)
    p = urlsplit(result)
    if origin(result) != origin(site_origin) or p.path != '/edit':
        raise ValueError('Native Edit href is not a local editor')
    if set(parse_qs(p.query, keep_blank_values=True)) - {'editor', 'node', 'way', 'relation'}:
        raise ValueError('Unexpected native editor query')
    if set(parse_qs(p.fragment, keep_blank_values=True)) - {'map', 'layers'}:
        raise ValueError('Unexpected native editor fragment')
    return result


def baseline_from_view(view):
    native_zoom(view)
    text = view.get('native_geo_uri', '')
    match = re.fullmatch(r'geo:([-+]?\d+(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)\?z=(\d+)', text)
    if not match:
        raise ValueError('Native settled initial view required')
    value = {'zoom': int(match[3]), 'lat': float(match[1]), 'lon': float(match[2])}
    # Validate numeric ranges using the same private-center contract as scoring.
    state_checks({'expected_center': value}, {}, 'http://127.0.0.1')
    return value


def validate(spec):
    """Strict scoring wrapper; expected center is optional and private."""
    if not isinstance(spec, dict) or set(spec) != {'version', 'state', 'reference_evidence'} or spec['version'] != VERSION:
        raise ValueError('Unsupported native editor contract')
    state_checks(spec['state'], {}, 'http://127.0.0.1')
    evidence = spec['reference_evidence']
    if not isinstance(evidence, list) or len(evidence) != 2:
        raise ValueError('Two independent native editor reference cycles required')
    if any(not isinstance(r, dict) or set(r) != {'file', 'sha256'} or
           not isinstance(r['file'], str) or not isinstance(r['sha256'], str) or
           not re.fullmatch('[0-9a-f]{64}', r['sha256']) for r in evidence):
        raise ValueError('Invalid native editor reference provenance')
    if len({str(Path(r['file']).resolve()) for r in evidence}) != 2:
        raise ValueError('Independent reference evidence cannot reuse one file')
    return spec


def validate_runtime(profile):
    required = {'version', 'community_fixture', 'presets_directory', 'presets_manifest_sha256',
                'local_tiles', 'native_source_sha256'}
    if (not isinstance(profile, dict) or set(profile) != required or profile['version'] != VERSION or
            profile['community_fixture'] != COMMUNITY_VERSION or profile['local_tiles'] is not True):
        raise ValueError('Explicit native local editor baseline profile required')
    if not isinstance(profile['presets_directory'], str) or not profile['presets_directory']:
        raise ValueError('Pinned local native editor presets required')
    hashes = profile['native_source_sha256']
    if (not isinstance(hashes, dict) or set(hashes) != set(NATIVE_FILES) or
            any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in hashes.values()) or
            not isinstance(profile['presets_manifest_sha256'], str) or
            not re.fullmatch('[0-9a-f]{64}', profile['presets_manifest_sha256'])):
        raise ValueError('Pinned native editor source and preset checksums required')
    return profile


def profile_for_contracts(contracts, domain):
    profiles = [c.get('map_editor_runtime') for c in contracts]
    enabled = [c.get('completion', {}).get('map_editor') is not None for c in contracts]
    if not any(enabled):
        if any(p is not None for p in profiles):
            raise ValueError('Editor profile supplied to non-editor task')
        return None
    if domain != 'map' or not all(enabled) or any(p != profiles[0] for p in profiles):
        raise ValueError('Native editor tasks require a dedicated Map manifest')
    validate_runtime(profiles[0])
    for c in contracts:
        validate(c['completion']['map_editor'])
        if c.get('map_community_fixture') != COMMUNITY_VERSION:
            raise ValueError('Editor account fixture must be explicitly bound')
        revision = c.get('environment_revision', {})
        if (revision.get('version') != COMMUNITY_VERSION or revision.get('synthetic_content') is not True or
                revision.get('original_benchmark_equivalence') is not False):
            raise ValueError('Local native editor initialization requires derivative provenance')
    return profiles[0]


def verify_reference(contract):
    """Read prior capability proof only as a reference, never as admission."""
    spec = validate(contract['completion']['map_editor'])
    start = local_path(contract['start_path'])
    expected = spec['state'].get('expected_center')
    observed_centers = []
    for ref in spec['reference_evidence']:
        file = Path(ref['file'])
        if hash_file(file) != ref['sha256']:
            raise RuntimeError('Native editor reference changed')
        row = json.loads(file.read_text())
        if (row.get('start_path') != start or row.get('passed') is not True or
                row.get('initialization_protocol') != INITIALIZATION or
                contract['source_task_id'] not in row.get('source_tasks', [])):
            raise RuntimeError('Reference is not bound to this source and original start')
        positive = row.get('positive', {})
        if positive.get('passed') is not True or positive.get('http_status') != 200:
            raise RuntimeError('Native editor reference positive failed')
        state = positive.get('state', {})
        site_url = state.get('outer_url')
        if not isinstance(site_url, str):
            raise RuntimeError('Native editor reference origin missing')
        p = urlsplit(site_url)
        site_origin = p.scheme + '://' + p.netloc
        if not all(state_checks(spec['state'], state, site_origin).values()):
            raise RuntimeError('Native editor reference does not meet this completion scope')
        if not all(row.get(key, {}).get('passed') is True for key in (
                'initial_negative', 'wrong_center_negative', 'login_negative', 'error_negative')):
            raise RuntimeError('Native editor capability reference negatives failed')
        if expected is not None:
            initial = baseline_from_view(row.get('initial_native_view'))
            initial_state = {'native_map': initial}
            if not state_checks({'expected_center': expected}, initial_state, site_origin)['requested_area']:
                raise RuntimeError('Requested area differs from independently observed initial view')
            observed_centers.append(initial)
    if expected is not None and observed_centers[0] != observed_centers[1]:
        raise RuntimeError('Independent native initial areas differ')
    return True


def verify_runtime(root, profile):
    profile = validate_runtime(profile)
    app = Path(root) / 'datasets/webarena-map-frontend/openstreetmap-website'
    if any(hash_file(app / rel) != sha for rel, sha in profile['native_source_sha256'].items()):
        raise RuntimeError('Native editor source drifted')
    from .map_editor_presets import checked_assets
    directory = Path(profile['presets_directory'])
    checked_assets(directory)
    if hash_file(directory / 'manifest.json') != profile['presets_manifest_sha256']:
        raise RuntimeError('Native preset manifest drifted')
    return True


def prepare_site(site, profile, *, browser=None):
    """Declare native OAuth/presets/tiles before baseline, then track all writes."""
    verify_runtime(site.root, profile)
    if (getattr(site, 'community_fixture', None) != COMMUNITY_VERSION or
            not getattr(site, 'reset_guard', None) or
            not site.state.is_relative_to(Path(site.temporary.name)) or site.rails_command[-5] != 'server'):
        raise ValueError('Fresh tracked disposable community site required')
    existing = getattr(site, '_map_native_editor_baseline', None)
    if existing is not None:
        if existing['profile'] != profile:
            raise RuntimeError('Native editor baseline profile changed on reused instance')
        site.reset_guard.require_unchanged()
        return dict(existing['proof'], verified_clean_reuse=True)
    state_before = checked_state(json.loads(site.app_sql(STATE_SQL)))
    if state_before['changed']:
        raise RuntimeError('Editor setup requires a clean post-fixture baseline')
    account_initialization = initialize_native_account(site, browser=browser)
    if checked_state(json.loads(site.app_sql(STATE_SQL)))['changed']:
        raise RuntimeError('Native account initialization did not leave a clean baseline')
    community_before = records(site)
    # Native User#oauth_token creates/reuses the local access token. No token,
    # application UID, OAuth DOM or iframe full hash is returned or logged.
    script = site.state / 'frontend/app/tmp/native-editor-baseline.rb'
    script.write_text('''require "yaml"
owner = User.find_by!(:display_name => "LocalBenchmarkMapper")
raise "Local application already exists" if Oauth2Application.where(:name => "Local capability iD").exists?
application = Oauth2Application.create!(:owner => owner, :name => "Local capability iD",
  :redirect_uri => "http://127.0.0.1", :confidential => false,
  :scopes => "read_prefs write_prefs write_api read_gpx write_gpx write_notes")
path = Rails.root.join("config/settings.local.yml")
settings = YAML.safe_load(File.read(path))
raise "Existing editor configuration" if settings.key?("id_application")
settings["id_application"] = application.uid
File.write(path, settings.to_yaml)
raise "Native token missing" unless owner.oauth_token(application.uid)
puts "Native local editor baseline configured; credentials omitted"
''')
    site.run(site.rails_command[:-5] + ['runner', '/app/tmp/native-editor-baseline.rb'],
             'prepare_native_editor_baseline', 180)
    from .map_editor_presets import install as install_presets
    from .map_editor_tiles import install as install_tiles
    presets = install_presets(site, profile['presets_directory'])
    tiles = install_tiles(site)
    site.restart_frontend(preserve_compiled_assets=True)
    changed = checked_state(json.loads(site.app_sql(STATE_SQL)))['changed']
    allowed = {'public.oauth_applications', 'public.oauth_access_tokens'}
    if set(changed) != allowed or records(site) != community_before:
        raise RuntimeError('Unexpected native editor initialization write')
    # Rebase only after verified declared initialization. Clear markers, so any
    # later OAuth write is again a new detected statement, not silently allowed.
    site.app_sql('TRUNCATE codex_reset_guard.changed;')
    site.reset_guard.initial = site.reset_guard.fingerprint()
    proof = {'version': VERSION, 'native_account_initialization': account_initialization, 'synthetic_account': True, 'fixture': COMMUNITY_VERSION,
             'original_benchmark_equivalence': False, 'initialization_changed_tables': changed,
             'initialization_only_oauth_writes': True, 'community_records_unchanged': True,
             'future_oauth_writes_tracked': True, 'initial_fingerprint': site.reset_guard.initial,
             'presets': presets, 'tiles': tiles,
             'scope': 'Native editor navigation only; no edits, saves or full imagery coverage.'}
    atomic_write_json(site.logs / 'native-editor-baseline.json', proof)
    site._map_native_editor_baseline = {'profile': json.loads(json.dumps(profile)),
                                      'proof': json.loads(json.dumps(proof))}
    return proof


def authenticate(page, site):
    """Private account bootstrap only, before the unchanged first task document."""
    response = page.goto(site.url + '/login', wait_until='domcontentloaded', timeout=60000)
    if response is None or response.status != 200:
        raise RuntimeError('Native local login unavailable')
    page.locator('#login_form input[name=username]').fill(USERNAME)
    page.locator('#login_form input[name=password]').fill(PASSWORD)
    page.locator('#login_form input[type=submit],#login_form button[type=submit]').click(timeout=15000)
    page.wait_for_url(lambda url: urlsplit(str(url)).path != '/login', timeout=30000)
    page.goto('about:blank', wait_until='domcontentloaded', timeout=15000)


def observe_initial(page, contract):
    """Observe native initialization; retain directions' native fit/pan behavior."""
    local_path(contract['start_path'])
    spec = validate(contract['completion']['map_editor'])
    requested = urlsplit(contract['start_path'])
    view = None
    if requested.path in ('/', '/directions') and parse_qs(requested.fragment).get('map'):
        view = wait_native_view(page, contract['start_path'])
    expected = spec['state'].get('expected_center')
    if expected is not None:
        initial = baseline_from_view(view)
        if not state_checks({'expected_center': expected}, {'native_map': initial}, page.url.split('/', 3)[0] + '//' + urlsplit(page.url).netloc)['requested_area']:
            raise RuntimeError('Initial area differs from independent native reference')
    return {'original_start_path': contract['start_path'], 'initialization_protocol': INITIALIZATION,
            'native_view': view, 'requested_area_verified': expected is None or view is not None}


def read_terminal(page, *, timeout=45000):
    """Bounded observation only; never waits for or forces an expected target area."""
    end = time.monotonic() + timeout / 1000
    last = None
    retries = 0
    from playwright.sync_api import TimeoutError as BrowserTimeout
    while time.monotonic() < end:
        try:
            last = read_editor_state(page)
        except Exception as exc:
            if not navigation_context_changed(exc) or page.is_closed():
                raise
            retries += 1
        else:
            outer = urlsplit(last['outer_url'])
            if outer.path != '/edit':
                last['readiness_timed_out'] = False
                last['navigation_read_retries'] = retries
                return last
            site_origin = outer.scheme + '://' + outer.netloc
            native = state_checks({}, last, site_origin)
            if all(native.values()):
                last['readiness_timed_out'] = False
                last['navigation_read_retries'] = retries
                return last
            # Missing configuration/embed is a real wrong terminal state, not
            # permission to spend a new budget waiting for an absent editor.
            if not last['configured'] or not last['embed_visible']:
                last['readiness_timed_out'] = False
                last['navigation_read_retries'] = retries
                return last
        remaining = max(0, (end - time.monotonic()) * 1000)
        if remaining:
            page.wait_for_timeout(min(100, remaining))
    if last is None:
        raise BrowserTimeout('Native editor document could not be observed')
    last['readiness_timed_out'] = True
    last['navigation_read_retries'] = retries
    return last


def terminal_checks(spec, state, site_origin, *, terminal_url):
    validate(spec)
    if not isinstance(state, dict):
        raise ValueError('Native editor terminal state missing')
    outer = state.get('outer_url')
    actual = urlsplit(terminal_url)
    if origin(outer) != origin(terminal_url) or urlsplit(outer).path != actual.path:
        raise ValueError('Native editor capture and terminal page differ')
    if state.get('readiness_timed_out') is True:
        raise ValueError('Native editor was still initializing at termination')
    return state_checks(spec['state'], state, site_origin)


def wrong_center_path(center):
    zoom, lat, lon = center['zoom'], center['lat'], center['lon']
    precision = max(0, math.ceil(math.log2(zoom)))
    delta = max(1, 4 * 10 ** -precision)
    lat = lat - delta if lat >= 0 else lat + delta
    return '/edit#map=' + '/'.join((format(zoom, 'g'), format(lat, '.8f'), format(lon, '.8f')))


def control_names(spec):
    validate(spec)
    names = ('hidden_editor', 'missing_editor')
    if 'expected_center' in spec['state']:
        names += ('wrong_editor_area',)
    return names


def normal_controls(browser, site, contract, capture_current):
    """Actual ordinary controls; no actor and no automatic task admission.

    Each task uses independent browser contexts and its unchanged initial path.
    A direct navigation to the observed native Edit href is a private positive
    control only. This does not prescribe a path for the actor.
    """
    verify_reference(contract)
    from .browser_request_policy import install_local_network_policy
    ctx = browser.new_context(viewport={'width': 1280, 'height': 720}, locale='en-US',
                              extra_http_headers={'Accept-Language': 'en-US'})
    cases, details = {}, {'native_editor_reference_verified': True,
                         'editor_initial_state_verified': False}
    def snapshot(page, response=None):
        state = capture_current(page, 'map', response=response)
        state['map_editor'] = read_terminal(page)
        return state
    try:
        install_local_network_policy(ctx, site.allowed_netlocs)
        page = ctx.new_page()
        page.set_default_timeout(15000)
        authenticate(page, site)
        response = page.goto(site.url + contract['start_path'], wait_until='domcontentloaded', timeout=60000)
        details['initial_editor_view'] = observe_initial(page, contract)
        details['editor_initial_state_verified'] = True
        cases['initial_no_op'] = snapshot(page, response)
        page.wait_for_function("() => document.querySelector('#edit_tab a')?.getAttribute('href')", timeout=30000)
        native = page.evaluate(EDIT_CONTROL)
        target = native_edit_url(site.url, native.get('href'))
        details['native_edit_control'] = native
        response = page.goto(target, wait_until='domcontentloaded', timeout=60000)
        cases['positive'] = snapshot(page, response)
        # Mutate only transient DOM to test real visibility, never forge the
        # capture dictionary and never alter or save geographic data.
        page.eval_on_selector('#id-embed', "e => e.style.display = 'none'")
        cases['hidden_editor'] = snapshot(page)
        page.eval_on_selector('#id-embed', "e => e.style.display = ''")
        cases['restored_positive'] = snapshot(page)
        page.eval_on_selector('#id-embed', 'e => e.remove()')
        cases['missing_editor'] = snapshot(page)
        if 'expected_center' in contract['completion']['map_editor']['state']:
            other = ctx.new_page()
            response = other.goto(site.url + wrong_center_path(
                contract['completion']['map_editor']['state']['expected_center']),
                wait_until='domcontentloaded', timeout=60000)
            cases['wrong_editor_area'] = snapshot(other, response)
            other.close()
        for key, path in (('wrong_target', '/about'), ('404', '/__native_editor_control_not_found__')):
            other = ctx.new_page()
            response = other.goto(site.url + path, wait_until='domcontentloaded', timeout=60000)
            cases[key] = snapshot(other, response)
            other.close()
        anon = browser.new_context(viewport={'width': 1280, 'height': 720}, locale='en-US',
                                   extra_http_headers={'Accept-Language': 'en-US'})
        try:
            install_local_network_policy(anon, site.allowed_netlocs)
            other = anon.new_page()
            response = other.goto(site.url + '/login', wait_until='domcontentloaded', timeout=60000)
            cases['login'] = snapshot(other, response)
        finally:
            anon.close()
    finally:
        ctx.close()
    return cases, details


def require_editor_admission(contract, cycles):
    """The earlier capability-only proof cannot stand in for normal admission."""
    profile_for_contracts([contract], contract.get('domain'))
    verify_reference(contract)
    expected = {'positive': 'success', 'restored_positive': 'success',
                **{k: 'failure' for k in ('initial_no_op', 'wrong_target', '404', 'login') +
                   control_names(contract['completion']['map_editor'])}}
    if len(cycles) != 2 or any(not any(
            row.get('task_id') == contract['task_id'] and
            row.get('native_editor_reference_verified') is True and
            row.get('editor_initial_state_verified') is True and
            all(row.get('checks', {}).get(k) == v for k, v in expected.items())
            for row in cycle.get('tasks', [])) for cycle in cycles):
        raise ValueError('Native editor requires normal visibility/area negatives and original-start verification in both cycles')


def base_contract(contract):
    """Copy only the optional editor adapter away for generic health checks."""
    result=dict(contract)
    result['completion']={k:v for k,v in contract['completion'].items() if k!='map_editor'}
    return result


def fingerprint(contract):
    """Bind native profile/reference and full original task to ordinary proof."""
    from .site_navigation_rules import contract_fingerprint
    profile_for_contracts([contract],contract.get('domain'))
    value={'generic_contract':contract_fingerprint(base_contract(contract)),
           'native_editor':contract['completion']['map_editor'],
           'native_editor_runtime':contract['map_editor_runtime']}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def evaluate(contract, page, *, site_origin):
    """Actual terminal scoring; an actor attempt in the wrong page is not success."""
    from .site_navigation_rules import evaluate_navigation
    generic=evaluate_navigation(base_contract(contract),page,site_origin=site_origin)
    if generic['status']!='success':
        return generic
    checks=dict(generic['checks'])
    try:
        checks.update(terminal_checks(contract['completion']['map_editor'],page.get('map_editor'),
                                     site_origin,terminal_url=page['url']))
    except (ValueError,TypeError,KeyError) as exc:
        return {**generic,'status':'unknown','success':False,'reward':None,'checks':checks,
                'reason':'Native editor terminal state is missing, inconsistent or still initializing.'}
    ok=all(checks.values())
    return {**generic,'status':'success' if ok else 'failure','success':ok,'reward':float(ok),'checks':checks}


def control_admission(contract, cases, *, site_origin):
    """Ordinary positive/negative controls, including real DOM visibility."""
    from .site_navigation_rules import control_admission as generic_control
    base=generic_control(base_contract(contract),cases,site_origin=site_origin)
    expected={'positive':'success','restored_positive':'success',
        **{name:'failure' for name in ('initial_no_op','wrong_target','404','login')+
          control_names(contract['completion']['map_editor'])}}
    if any(name not in cases for name in expected):
        return {**base,'passed':False,'status':'missing_editor_controls','checks':{}}
    judgments={name:evaluate(contract,page,site_origin=site_origin) for name,page in cases.items()}
    passed=base['passed'] and all(judgments[name]['status']==status for name,status in expected.items())
    return {**base,'passed':passed,'status':'passed' if passed else 'editor_contract_or_control_mismatch',
            'checks':{name:row['status'] for name,row in judgments.items()}}


def require_admission(contract, proof):
    """Validate normal proof; prior capability passes cannot authorize an actor."""
    from .site_navigation_rules import require_admission as generic_require, contract_fingerprint
    if proof.get('contract_fingerprint')!=fingerprint(contract):
        raise ValueError('Native editor admission is bound to a different task/start/profile/reference')
    projected=dict(proof,contract_fingerprint=contract_fingerprint(base_contract(contract)))
    generic_require(base_contract(contract),projected)
    require_editor_admission(contract,proof.get('cycles',[]))
