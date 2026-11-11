"""Full native Map website with an instance-owned genuine signup inbox.

No account, token, or confirmation is synthesized. Dirty account/database/mail
state requires a cold deployment; this class never clears write guards or
selectively deletes account rows to pretend a reset occurred.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import stat

from .map_query_site import IsolatedMapQuerySite
from .map_account_mail import install
from .map_account_inbox import LocalAccountInbox
from .map_account_inbox_frontend import NativeInboxExtension
from .map_reset_guard import MapStateChanged
from .io_utils import atomic_write_json


def mail_state(directory):
    """Include unfinished writes too; an empty visible inbox is not a reset."""
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Private regular mail directory required')
    files = sorted(root.iterdir())
    if len(files) > 128:
        raise ValueError('Local mailbox exceeds bounded reset-check budget')
    rows = []
    for path in files:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
            raise ValueError('Bounded regular native mail file required')
        body = path.read_bytes()
        after = path.lstat()
        identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(body) > 1024 * 1024 or identity(after) != identity(info):
            raise MapStateChanged('Native mail write still in progress')
        rows.append(dict(name=path.name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
    if [p.name for p in sorted(root.iterdir())] != [r['name'] for r in rows]:
        raise MapStateChanged('Mailbox changed during reset check')
    return rows


class IsolatedMapAccountSite(IsolatedMapQuerySite):
    def __init__(self, root, logs, *, account):
        if (not isinstance(account, dict) or set(account) != {'email', 'display_name', 'password'}
                or not all(isinstance(v, str) and v for v in account.values())
                or not account['email'].endswith('@example.test')):
            raise ValueError('Explicit local training account required')
        self.account = deepcopy(account)
        self.inbox = self.extension = self.outbox = None
        self.mail_initial = None
        self.account_baseline = None
        super().__init__(root, logs, with_tiles=True, with_geographic_baseline=True, track_changes=True)

    def launch(self, command, name):
        if name == 'rails_server' and self.inbox is None:
            self.outbox = install(self.state / 'frontend')
            self.mail_initial = mail_state(self.outbox)
            if self.mail_initial:
                raise ValueError('New isolated account inbox must be empty')
            self.inbox = LocalAccountInbox(self.outbox, recipient=self.account['email'],
                                          display_name=self.account['display_name'], origin=self.url)
            self.extension = NativeInboxExtension(self.state / 'frontend', self.inbox)
            self.extension.install()
        return super().launch(command, name)

    def require_owned_inbox(self):
        if (self.inbox is None or self.extension is None or self.inbox.closed
                or not self.inbox.thread.is_alive() or self.inbox.outbox != self.outbox
                or self.inbox.account != dict(recipient=self.account['email'],
                    display_name=self.account['display_name'], origin=self.url)):
            raise ValueError('Private account inbox ownership changed')
        for path, payload in self.extension.installed.items():
            if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
                raise ValueError('Installed native inbox source changed')
        if len(self.extension.installed) != 3:
            raise ValueError('Incomplete native inbox extension')

    def __enter__(self):
        super().__enter__()
        try:
            self.require_owned_inbox()
            self.account_baseline = self.fingerprint()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def fingerprint(self):
        self.require_owned_inbox()
        # Exclude ephemeral service ports but bind account identity and actual
        # mail bytes. Base fingerprint covers all public DB writes/sequences
        # and persistent public/storage files.
        value = dict(native=super().fingerprint(), account=self.account,
                     mail=mail_state(self.outbox), profile='map-local-account-inbox-v1')
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    def reset_state(self):
        self.require_owned_inbox()
        if (mail_state(self.outbox) != self.mail_initial or self.inbox.snapshot()['messages']
                or self.fingerprint() != self.account_baseline):
            raise MapStateChanged('Account/mail state changed; complete cold deployment required')
        super().reset_state()
        self.require_owned_inbox()
        if self.fingerprint() != self.account_baseline:
            raise MapStateChanged('Account baseline changed during native restart')

    def __exit__(self, *args):
        failure = None
        receipt = None
        processes = list(self.active)
        try:
            if self.inbox is not None:
                if 'rails_server' in self.named_processes:
                    self.stop_service('rails_server')
                # Capture small private receipts before node-local teardown;
                # the runner separately persists the MIME bodies when needed.
                receipt = dict(inbox=self.inbox.snapshot(), files=mail_state(self.outbox),
                               cleanup_completed=False)
                atomic_write_json(self.logs / 'account-mail-exit.json', receipt)
                if self.extension is not None:
                    self.extension.close()
                    self.extension = None
        except BaseException as exc:
            failure = exc
        finally:
            try:
                if self.inbox is not None:
                    self.inbox.close()
            finally:
                super().__exit__(*args)
        if receipt is not None:
            receipt.update(inbox=self.inbox.snapshot(),
                           native_processes_stopped=all(p.poll() is not None for p in processes),
                           extension_restored=self.extension is None,
                           ports_released=self.ports is None,
                           cleanup_completed=failure is None)
            atomic_write_json(self.logs / 'account-mail-exit.json', receipt)
        if failure is not None:
            raise failure
