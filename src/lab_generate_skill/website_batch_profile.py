"""Validate and partition website configuration before allocating an actor."""
import json


def optional_worker_options(optional):
    """Forward every declared optional environment profile to SiteWorker.

    A new family must never be accepted by dispatch but silently dropped when
    the ordinary runner constructs its website. Mail is already combined with
    the legacy newsletter flag in profile().
    """
    keys={'shopping_capture_mail','map_account','map_existing_account','map_reader_diaries','map_saved_node_editor',
          'map_short_routes','map_raster_export','map_pdf_export','map_raster_query_policy','map_location_observer'}
    if not isinstance(optional,dict) or set(optional)-keys:
        raise ValueError('Unsupported optional website worker configuration')
    return {k:v for k,v in optional.items()if k!='shopping_capture_mail'}


def profile(rows, domain):
    from .gitlab_declared_profiles import profile_for_contracts as gitlab_initial
    from .map_community_fixture import profile_for_contracts as community
    from .map_navigation_runtime import profile_for_contracts as navigation
    from .map_native_layer_runtime import profile_for_contracts as layers
    from .native_goal_dispatch import website_profile_for_contracts as optional
    if not rows or any(row['domain'] != domain for row in rows):
        raise ValueError('A nonempty single-site manifest is required')
    capture_mail = any(row.get('newsletter') for row in rows)
    if capture_mail and not all(row.get('newsletter') for row in rows):
        raise ValueError('Newsletter mail profile requires a dedicated manifest')
    community_profile = community(rows, domain)
    editor_profile = navigation(rows, domain)
    optional_profile = optional(rows, domain)
    cache_profiles = []
    for row in rows:
        value = row.get('gitlab_cache_initialization')
        if row.get('gitlab_persisted_goal'):
            from .gitlab_persisted_goal_runtime import enabled
            enabled(row)
            if value not in (None, 'wiki_issue'):
                raise ValueError('Persisted GitLab goals require the verified wiki_issue baseline')
            value = 'wiki_issue'
        cache_profiles.append(value)
    cache_profile = cache_profiles[0]
    if any(value != cache_profile for value in cache_profiles):
        raise ValueError('Native cache initialization requires a dedicated GitLab manifest')
    initial_profile = gitlab_initial(rows, domain)
    if cache_profile is not None and (domain != 'gitlab' or cache_profile not in ('wiki_issue','calendar_wiki_issue') or initial_profile is not None):
        raise ValueError('Native cache profile must use a separate plain GitLab baseline')
    return dict(capture_mail=capture_mail or optional_profile.get('shopping_capture_mail', False),
                community=community_profile, editor=editor_profile,
                optional=optional_profile, layers=layers(rows, domain),
                gitlab_initial=initial_profile, gitlab_cache=cache_profile)


def partition(rows, domain):
    """Keep incompatible fixtures isolated; never change any task definition."""
    groups = []
    for row in rows:
        value = profile([row], domain)  # Invalid individual contracts still fail.
        key = json.dumps(value, sort_keys=True)
        for group in groups:
            if group['key'] != key:
                continue
            candidate = group['rows'] + [row]
            try:
                combined = profile(candidate, domain)
            except ValueError:
                continue  # A family may additionally require a dedicated manifest.
            if combined == value:
                group['rows'].append(row)
                break
        else:
            groups.append(dict(key=key, profile=value, rows=[row]))
    return groups


def consecutive_service_counts(waves, domain):
    """Count only adjacent manifests compatible with one service lifetime.

    Keep the count stable throughout that lifetime so a shrinking remainder
    does not change the pool configuration and accidentally restart services.
    """
    counts = []
    index = 0
    while index < len(waves):
        rows = list(waves[index])
        expected = profile(rows, domain)
        stop = index + 1
        while stop < len(waves):
            candidate = rows + waves[stop]
            try:
                same = profile(candidate, domain) == expected
            except ValueError:
                same = False
            if not same:
                break
            rows = candidate
            stop += 1
        counts.extend([len(rows)] * (stop - index))
        index = stop
    return counts
