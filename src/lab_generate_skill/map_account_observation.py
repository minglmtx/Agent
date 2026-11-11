"""Native signup observations, with intended account writes separated from reset.

The website owner must cold-recreate after any write. These hooks never clear
write guards, reset a database, consume mail, or log in on behalf of an actor.
"""
from copy import deepcopy
from pathlib import Path
import json
from .io_utils import atomic_write_json as save
from .map_candidate_start import InitialStartHooks
from .map_account_terminal import evaluate_account
from .map_account_readout import account_snapshot, session_identity
from .map_query_site import IsolatedMapQuerySite
from .map_reset_guard import STATE_SQL, checked_state, persistent_files

ALLOWED_TABLES = {'public.users', 'public.user_tokens', 'public.user_preferences'}
ALLOWED_SEQUENCES = {'users_id_seq', 'user_tokens_id_seq'}


def protected_users(site, ids=None):
    if ids is not None:
        # Imported OSM baselines include system users with IDs -1 and 0.
        # Protect them too; only the database integer type/range is constrained.
        if any(type(i) is not int or not -(2**63) <= i < 2**63 for i in ids):
            raise ValueError('Native user ids required')
        if not ids:
            return []
        where = ' WHERE u.id IN (' + ','.join(str(i) for i in ids) + ')'
    else:
        where = ''
    value = json.loads(site.app_sql("SELECT coalesce(json_agg(x),'[]'::json) FROM "
        "(SELECT u.id,md5(to_jsonb(u)::text) AS sha FROM users u" + where + " ORDER BY u.id LIMIT 1001) x;"))
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError('Account baseline exceeds bounded existing-user protection')
    return value


def write_integrity(before, after, *, files_unchanged, users_unchanged):
    before, after = checked_state(before), checked_state(after)
    if before['changed'] or before['tables'] != after['tables']:
        return False
    initial, final = dict(before['sequences']), dict(after['sequences'])
    return (files_unchanged is True and users_unchanged is True
            and set(after['changed']) <= ALLOWED_TABLES
            and initial.keys() == final.keys()
            and all(initial[k] == final[k] for k in initial if k not in ALLOWED_SEQUENCES))


class AccountObservationHooks(InitialStartHooks):
    def __init__(self, candidate, directory, *, baseline):
        if candidate.get('candidate_completion', {}).get('family') != 'account_signup':
            raise ValueError('Declared native signup profile required')
        super().__init__(deepcopy(candidate), None)
        self.directory, self.baseline = Path(directory), baseline
        self.page = self.before = self.after = self.session = None
        self.capture_error = None
        self.closed = self.scored = False

    def prepare(self, site, username):
        account = self.candidate['candidate_completion']['public_account']
        if self.site is not None or username is not None or site.domain != 'map' or site.account != account:
            raise ValueError('One matching anonymous account site required')
        site.require_owned_inbox()
        site.reset_guard.require_unchanged()
        if IsolatedMapQuerySite.fingerprint(site) != self.baseline:
            raise ValueError('Full account native baseline changed')
        if site.fingerprint() != site.account_baseline:
            raise ValueError('Account/mail baseline is not clean')
        self.before = account_snapshot(site, account['email'])
        if self.before['target'] is not None:
            raise ValueError('Signup target already exists')
        self.guard_before = checked_state(json.loads(site.app_sql(STATE_SQL)))
        self.files_before = persistent_files(site.state/'frontend/app')
        self.users_before = protected_users(site)
        self.site = site
        self.events.append('prepare')

    def observe_initial(self, page):
        if self.page is not None:
            raise ValueError('One original account initial page required')
        super().observe_initial(page)
        self.page = page
        save(self.directory/'account-initial.json', dict(original_start=self.initial,
            account=self.before, guard=self.guard_before, protected_users=self.users_before))

    def capture_terminal(self, page, terminal):
        if self.closed or self.scored or page is not self.page:
            raise ValueError('Bound actor terminal page required')
        super().capture_terminal(page, terminal)
        try:
            # Same cookies, separate tab, native GET only; no hidden confirmation.
            self.session = session_identity(self.context, self.site.url)
            self.after = account_snapshot(self.site, self.site.account['email'])
        except Exception as error:
            self.capture_error = type(error).__name__ + ': account/session capture unavailable'

    def close(self):
        if not self.closed:
            super().close()
            self.closed = True

    def score_terminal(self, site, terminal, *, runtime_error=None):
        if site is not self.site or self.scored or not self.closed or self.terminal is None or terminal != self.terminal:
            raise ValueError('One terminal account score after actor context closure required')
        self.scored = True
        self.events.append('score_terminal')
        integrity = False
        protection = {}
        protection_stage = 'inbox_ownership'
        try:
            site.require_owned_inbox()
            protection_stage = 'write_guard'
            after = checked_state(json.loads(site.app_sql(STATE_SQL)))
            protection['guard'] = after
            protection_stage = 'persistent_files'
            protection['persistent_files_unchanged'] = persistent_files(site.state/'frontend/app') == self.files_before
            protection_stage = 'existing_users'
            protection['existing_users_unchanged'] = protected_users(site, [r['id'] for r in self.users_before]) == self.users_before
            protection_stage = 'write_integrity'
            integrity = write_integrity(self.guard_before, after,
                files_unchanged=protection['persistent_files_unchanged'],
                users_unchanged=protection['existing_users_unchanged'])
        except Exception as error:
            protection['error'] = type(error).__name__ + ': account instance protection unavailable'
            protection['error_stage'] = protection_stage
        judgment = evaluate_account(self.candidate['candidate_completion'], initial=self.before,
            final=self.after, session=self.session, origin=site.url, runtime_error=runtime_error,
            capture_error=self.capture_error, integrity=integrity)
        # Preserve the raw mail once, not its bearer URLs in summary/feedback.
        messages = []
        try:
            from .map_account_site import mail_state
            for item in mail_state(site.outbox):
                dest = self.directory/'account-mail'/item['name']
                dest.parent.mkdir(exist_ok=True)
                body = (site.outbox/item['name']).read_bytes()
                import hashlib
                if len(body) != item['bytes'] or hashlib.sha256(body).hexdigest() != item['sha256']:
                    raise ValueError('Mail changed during checkpoint')
                dest.write_bytes(body)
                messages.append(dict(item, artifact=str(dest.relative_to(self.directory))))
        except Exception as error:
            # Evidence persistence failure must not publish a positive reward.
            self.capture_error = type(error).__name__ + ': mail checkpoint unavailable'
            judgment = evaluate_account(self.candidate['candidate_completion'], initial=self.before,
                final=self.after, session=self.session, origin=site.url,
                capture_error=self.capture_error, integrity=integrity)
        save(self.directory/'account-terminal.json', dict(events=self.events, terminal=terminal,
            initial=self.before, final=self.after, session=self.session, protection=protection,
            capture_error=self.capture_error, integrity=integrity, mail=messages, judgment=judgment,
            cold_reset_required=True))
        return judgment, integrity
