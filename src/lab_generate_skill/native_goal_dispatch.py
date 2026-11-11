"""Optional hook dispatch; existing native reads retain their implementation.

The normal runner can reuse its current terminal-only hook slot. This changes
no actor inputs or action protocol and does not perform mid-rollout judging.
"""
from . import shopping_cart_view_runtime as cart_view
from . import shopping_page_visit_runtime as page_visits
from . import gitlab_native_read_runtime as reads
from . import gitlab_navigation_goal_runtime as navigation
from . import preference_goal_state_runtime as preferences
from . import reddit_explicit_submission_runtime as submissions
from . import shopping_offline_training_runtime as shopping_offline
from . import gitlab_grouped_goal_runtime as grouped
from . import gitlab_group_import_runtime as group_import
from . import map_native_route_runtime as native_routes
from . import map_native_facts_runtime as native_facts
from . import reddit_final_read_runtime as final_reddit
from . import shopping_complete_training_query_runtime as complete_queries

from . import gitlab_persisted_goal_runtime as persisted
from . import gitlab_boundary_goal_runtime as boundary
from . import gitlab_explore_visit_goal_runtime as explore_visits

from . import map_initial_view_link_runtime as initial_links

from . import reddit_search_completion_runtime as search_completion
from . import public_completion_runtime as public_completion
from . import public_navigation_revision as public_navigation

# Frozen worker bootstraps may install reviewed family adapters. Contracts never
# name Python modules or supply constructors; existing families cannot be replaced.
_additional_protocols = {}
_admission_bridges = {}
_shared_feedback_owners = {}


def register_protocol(name, module, *, feedback_owner=None):
    return _register_protocol(name,module,feedback_owner=feedback_owner)


def _register_protocol(name, module, inherited_versions=(), feedback_owner=None):
    if not isinstance(name, str) or not name or name in _additional_protocols:
        raise ValueError('A distinct native protocol registration is required')
    required = ('enabled', 'require_admission', 'require_original_binding',
                'NativeReadHooks', 'public_goal', 'fields', 'feedback')
    if any(not callable(getattr(module, key, None)) for key in required):
        raise ValueError('Complete normal native lifecycle adapter required')
    versions = getattr(module, 'FEEDBACK_VERSIONS', ())
    if not versions or any(not isinstance(v, str) or not v for v in versions):
        raise ValueError('Explicit feedback versions required')
    builtins = (public_navigation, public_completion, search_completion, initial_links, explore_visits, boundary,
                persisted, page_visits, cart_view, navigation, preferences,
                grouped, group_import, submissions, shopping_offline, native_routes,
                native_facts.facts, final_reddit, final_reddit.original,
                final_reddit.maximum, complete_queries, reads)
    builtin_versions = {getattr(m, 'VERSION', None) for m in builtins}
    builtin_versions.update(native_routes.FEEDBACK_VERSIONS)
    if set(versions) & (builtin_versions-set(inherited_versions)):
        raise ValueError('Existing native feedback protocol cannot be replaced')
    for other_name, other in _additional_protocols.items():
        if not set(versions) & set(other.FEEDBACK_VERSIONS):
            continue
        # Only explicitly co-owned, stateless standard feedback may share a
        # version. This does not merge lifecycle selection or write policies.
        from .frozen_native_family_adapter import FrozenNativeFamilyAdapter
        expected = FrozenNativeFamilyAdapter.feedback
        if (feedback_owner is None or _shared_feedback_owners.get(other_name) is not feedback_owner
                or getattr(module.feedback, '__func__', None) is not expected
                or getattr(other.feedback, '__func__', None) is not expected):
            raise ValueError('Duplicate native feedback version')
    if type(getattr(module, 'AUTHORIZED_TARGET_WRITES', False)) is not bool:
        raise ValueError('Explicit target write policy required')
    _additional_protocols[name] = module
    if feedback_owner is not None:_shared_feedback_owners[name] = feedback_owner


def register_admission_bridge(name, module, *, base_protocol, feedback_owner=None):
    """Bind an original full-proof driver to an existing predicate family.

    Only a trusted frozen bootstrap can install this bridge. Contracts cannot
    select it. The adapter retains exact source binding and replays its complete
    original admission gate before constructing any ordinary hooks. Existing
    feedback handlers are not replaced.
    """
    from .frozen_native_family_adapter import FrozenNativeFamilyAdapter
    if not isinstance(module, FrozenNativeFamilyAdapter):
        raise ValueError('An original full-proof native adapter is required')
    if base_protocol is not grouped:
        raise ValueError('No reviewed admission bridge for this base protocol')
    _register_protocol(name,module,inherited_versions=(base_protocol.VERSION,),feedback_owner=feedback_owner)
    _admission_bridges[name] = (module, base_protocol)


def unregister_protocol(name, module):
    if _additional_protocols.get(name) is not module:
        raise ValueError('Only the owner may unregister a native protocol')
    del _additional_protocols[name]
    _admission_bridges.pop(name, None)
    _shared_feedback_owners.pop(name, None)


def protocol(contract):
    kinds = [m for m in (public_navigation, public_completion, search_completion, initial_links, explore_visits, boundary, persisted, page_visits, cart_view, navigation, preferences, grouped, group_import, submissions, shopping_offline, native_routes, native_facts, final_reddit, complete_queries, reads) if m.enabled(contract)]
    kinds.extend(m for m in _additional_protocols.values() if m.enabled(contract))
    for name, (adapter, base) in _admission_bridges.items():
        if (_additional_protocols.get(name) is adapter
                and any(m is adapter for m in kinds)
                and not any(m is base for m in kinds)):
            raise ValueError('Admission bridge does not match its native predicate family')
    if len(kinds) == 2:
        for name, (adapter, base) in _admission_bridges.items():
            if (_additional_protocols.get(name) is adapter
                    and any(m is adapter for m in kinds)
                    and any(m is base for m in kinds)):
                return adapter
    if len(kinds) > 1: raise ValueError('Only one optional native goal lifecycle may be enabled')
    return kinds[0] if kinds else None

def enabled(contract):
    return protocol(contract) is not None

def owns_csv_transport(contract):
    """Only the registered implementation can declare transport ownership."""
    module = protocol(contract)
    owned = getattr(module, 'OWNS_NATIVE_CSV_TRANSPORT', False)
    if type(owned) is not bool:
        raise ValueError('Invalid native CSV lifecycle ownership')
    if owned and (contract.get('domain') != 'gitlab' or not isinstance(contract.get('native_csv_export'), dict)):
        raise ValueError('CSV lifecycle owner requires a native CSV contract')
    return owned

def require_admission(contract, proof):
    module = protocol(contract)
    if module is None: raise ValueError('No optional native goal protocol declared')
    return module.require_admission(contract, proof)

def require_original_binding(contract, original, inventory):
    module = protocol(contract)
    if module is None: raise ValueError('No optional native goal protocol declared')
    return module.require_original_binding(contract, original, inventory)

def NativeReadHooks(contract, proof, directory):
    module = protocol(contract)
    if module is public_navigation: return public_navigation.NativeReadHooks(contract, proof, directory)
    if module is public_completion: return public_completion.NativeReadHooks(contract, proof, directory)
    if any(module is m for m in _additional_protocols.values()):
        module.require_admission(contract, proof)
        return module.NativeReadHooks(contract, proof, directory)
    if module is search_completion: return search_completion.SearchCompletionHooks(contract, proof, directory)
    if module is initial_links: return initial_links.InitialViewLinkHooks(contract, proof, directory)
    if module is persisted: return persisted.PersistedGoalHooks(contract, proof, directory)
    if module is boundary: return boundary.BoundaryGoalHooks(contract, proof, directory)
    if module is explore_visits: return explore_visits.ExploreVisitHooks(contract, proof, directory)
    if module is page_visits: return page_visits.PageVisitHooks(contract, directory, proof=proof)
    if module is cart_view: return cart_view.CartViewHooks(contract, proof, directory)
    if module is navigation: return navigation.NavigationGoalHooks(contract, proof, directory)
    if module is preferences: return preferences.PreferenceGoalStateHooks(contract, proof, directory)
    if module is submissions: return submissions.ExplicitSubmissionHooks(contract, proof, directory)
    if module is shopping_offline: return shopping_offline.ShoppingOfflineHooks(contract, proof, directory)
    if module is grouped: return grouped.GroupedGoalHooks(contract, proof, directory)
    if module is group_import: return group_import.NativeReadHooks(contract, proof, directory)
    if module is native_routes: return native_routes.NativeRouteReadHooks(contract, proof, directory)
    if module is native_facts: return native_facts.NativeFactsReadHooks(contract, proof, directory)
    if module is final_reddit: return final_reddit.FinalReadingHooks(contract, proof, directory)
    if module is complete_queries: return complete_queries.CompleteNativeQueryHooks(contract, proof, directory)
    if module is reads: return reads.NativeReadHooks(contract, proof, directory)
    raise ValueError('No optional native goal protocol declared')

def feedback(judgment):
    version = judgment.get('version')
    if version == public_navigation.VERSION: return public_navigation.feedback(judgment)
    if version == public_completion.VERSION: return public_completion.feedback(judgment)
    for module in _additional_protocols.values():
        if version in module.FEEDBACK_VERSIONS:
            return module.feedback(judgment)
    if version == search_completion.VERSION: return search_completion.feedback(judgment)
    if version == initial_links.VERSION: return initial_links.feedback(judgment)
    if version == persisted.VERSION: return persisted.feedback(judgment)
    if version == boundary.VERSION: return boundary.feedback(judgment)
    if version == explore_visits.VERSION: return explore_visits.feedback(judgment)
    if version == page_visits.VERSION: return page_visits.feedback(judgment)
    if version == cart_view.VERSION: return cart_view.feedback(judgment)
    if version == complete_queries.VERSION: return complete_queries.feedback(judgment)
    if version in native_routes.FEEDBACK_VERSIONS: return native_routes.feedback(judgment)
    if version == native_facts.facts.VERSION: return native_facts.feedback(judgment)
    if version == navigation.VERSION: return navigation.feedback(judgment)
    if version == preferences.VERSION: return preferences.feedback(judgment)
    if version == submissions.VERSION: return submissions.feedback(judgment)
    if version == shopping_offline.VERSION: return shopping_offline.feedback(judgment)
    if version == grouped.VERSION: return grouped.feedback(judgment)
    if version == group_import.VERSION: return group_import.feedback(judgment)
    if version in (final_reddit.VERSION, final_reddit.original.VERSION, final_reddit.maximum.VERSION): return final_reddit.feedback(judgment)
    return reads.feedback(judgment)


def fields(contract):
    module=protocol(contract)
    hook=getattr(module,"fields",None)
    return hook(contract) if hook else []

def public_field_spec(contract):
    """Public names/types only; native private references are not schema inputs."""
    from collections.abc import Mapping
    names = fields(contract) or []
    hook = getattr(protocol(contract), 'answer_field_spec', None)
    declared = hook(contract) if hook is not None else names
    if hook is None and not isinstance(declared, Mapping):
        query_fields = (contract.get('query') or {}).get('fields')
        if isinstance(query_fields, Mapping) and set(query_fields) == set(names):
            declared = query_fields
    if isinstance(declared, Mapping):
        if (set(declared) != set(names)
                or any(not isinstance(v, str) or not v for v in declared.values())):
            raise ValueError('Native public answer schema differs from declared fields')
        return {name: declared[name] for name in names}
    if hook is not None:
        raise ValueError('Native public answer schema must map names to public types')
    return declared


def public_goal(contract):
    module=protocol(contract)
    hook=getattr(module,"public_goal",None)
    if hook is not None: return hook(contract)
    if contract.get("query"):
        from .site_query_rules import query_goal
        return query_goal(contract)
    return contract["goal"]


def guest_session(contract):
    """A validated native family may preserve its declared guest start."""
    module = protocol(contract)
    hook = getattr(module, 'guest_session', None)
    value = hook(contract) if hook is not None else False
    if type(value) is not bool or value and contract.get('private_authentication') != 'guest':
        raise ValueError('Explicit native guest initialization declaration required')
    return value


def website_profile_for_contracts(contracts, domain):
    """Optional local startup profile; no actor inputs or network changes.

    Family-owned profile validation receives the entire same-site manifest,
    so a local-mail family cannot quietly change a mixed worker's website.
    """
    rows = list(contracts)
    if any(c.get('domain') != domain for c in rows):
        raise ValueError('Website startup profile requires a same-site manifest')
    # Reviewed adapters need not be hashable (e.g. SimpleNamespace). A family
    # owns one adapter instance, so call its profile hook once by identity,
    # without comparing or hashing its implementation fields.
    modules = []
    for contract in rows:
        module = protocol(contract)
        if module is not None and not any(module is item for item in modules):
            modules.append(module)
    profile = {}
    for module in modules:
        hook = getattr(module, 'profile_for_contracts', None)
        if hook is None:
            continue
        value = hook(rows)
        # SiteWorker already owns this offline native profile. This adapter
        # translates the family hook into its existing explicit constructor.
        if not isinstance(value, dict):
            raise ValueError('Invalid optional website startup profile')
        update = value
        account_keys={'map_account','map_existing_account'}
        reader_keys={'map_reader_diaries'}
        editor_keys={'map_saved_node_editor'}
        if set(update) - ({'shopping_capture_mail','map_short_routes','map_raster_export','map_pdf_export','map_raster_query_policy','map_location_observer'}|account_keys|reader_keys|editor_keys):
            raise ValueError('Undeclared optional website startup profile')
        if any(type(v) is not bool for k,v in update.items() if k not in account_keys|reader_keys|editor_keys|{'map_raster_query_policy'}):
            raise ValueError('Invalid optional website startup setting')
        if 'map_raster_query_policy' in update and update['map_raster_query_policy'] not in ('default','stable-scan'):
            raise ValueError('Invalid renderer query policy')
        if account_keys & set(update):
            from .map_account_profile import validate_account
            if domain!='map':raise ValueError('Local account is a Map profile')
            update={k:validate_account(v)if k in account_keys else v for k,v in update.items()}
        if reader_keys & set(update):
            from .map_reader_v187.profile import validate_profile
            if domain!='map':raise ValueError('Native reader/diary fixture is a Map profile')
            update={k:validate_profile(v)if k in reader_keys else v for k,v in update.items()}
        if editor_keys & set(update):
            from .map_edit_v190.profile import validate_profile
            if domain!='map' or len(rows)!=1 or set(update)!=editor_keys:
                raise ValueError('A single native saved-node source must own its dedicated Map profile')
            update={k:validate_profile(v) for k,v in update.items()}
        for key, value in update.items():
            if key in profile and profile[key] != value:
                raise ValueError('Conflicting optional website startup profiles')
            profile[key] = value
    if profile.get('shopping_capture_mail') and domain != 'shopping':
        raise ValueError('Local mail capture is a Shopping profile')
    if profile.get('map_short_routes') and domain != 'map':
        raise ValueError('Compact routes are a Map profile')
    if profile.get('map_raster_export') and domain != 'map':
        raise ValueError('PNG export is a Map profile')
    if profile.get('map_pdf_export') and (domain!='map' or profile.get('map_raster_export')is not True):
        raise ValueError('PDF export requires the dedicated Map renderer profile')
    if 'map_raster_query_policy' in profile and (domain!='map' or profile.get('map_raster_export')is not True):
        raise ValueError('Renderer policy requires the dedicated Map renderer profile')
    if 'map_saved_node_editor'in profile and set(profile)!={'map_saved_node_editor'}:
        raise ValueError('Native saved-node editing cannot share another optional profile')
    if 'map_reader_diaries'in profile and set(profile)!={'map_reader_diaries'}:
        raise ValueError('Native reader/diary fixture cannot share other optional profiles')
    if 'map_account'in profile and 'map_existing_account'in profile:
        raise ValueError('Signup and existing-account fixtures cannot share a manifest')
    return profile


def terminal_integrity(contract, *, selected_unchanged, native_unchanged,
                       auxiliary_unchanged=True):
    """A module's strict complete protection owns its declared target writes.

    Read-only and existing lifecycle modules retain the selected-record guard.
    This slot is usable only after that module's full admission and terminal
    validation; incomplete native capture always rejects, including for writes.
    """
    module = protocol(contract)
    authorized = getattr(module, 'AUTHORIZED_TARGET_WRITES', False)
    if type(authorized) is not bool or any(type(x) is not bool for x in
            (selected_unchanged, native_unchanged, auxiliary_unchanged)):
        raise ValueError('Explicit boolean protection results required')
    return native_unchanged and auxiliary_unchanged and (authorized or selected_unchanged)


def upload_files(contract, hooks):
    module = protocol(contract)
    hook = getattr(module, "upload_files", None)
    return hook(contract, hooks) if hook else []
