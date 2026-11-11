"""Validate a public native subscription URL without discarding real filters."""
from urllib.parse import parse_qs, urlsplit

from .gitlab_local_artifacts_v2 import local_native_url


def native_subscription_query(url, *, origin, contract, username):
    native = local_native_url(url, origin, calendar=contract['kind'] == 'calendar')
    part = urlsplit(native)
    if part.path != contract['feed_path']:
        raise ValueError('Wrong native subscription resource')
    query = parse_qs(part.query, keep_blank_values=True)
    tokens = query.pop('feed_token', [])
    if len(tokens) > 1 or any(not value for value in tokens):
        raise ValueError('Ambiguous native feed credential')
    expected = {key: [value.replace('{authenticated_username}', username) for value in values]
                for key, values in contract['feed_filters'].items()}
    # The native calendar helper supplies this ordering. Keep it for the
    # independent finder (the calendar has a 100-event limit); do not strip it
    # and accidentally inspect a different set. Other extra filters still fail.
    scope = dict(query)
    sort = scope.pop('sort', None) if contract['kind'] == 'calendar' else None
    if sort is not None and sort != ['closest_future_date']:
        raise ValueError('Unverified native calendar ordering')
    if scope != expected:
        raise ValueError('Native subscription filters differ from the public scope')
    if any(len(values) != 1 for values in query.values()):
        raise ValueError('Ambiguous native subscription parameters')
    return {key: values[0] for key, values in query.items()}
