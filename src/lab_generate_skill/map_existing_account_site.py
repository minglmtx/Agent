"""Explicit existing-account fixture, installed before any reset baseline.

This profile is for login derivatives only. No browser is authenticated during
initialization. A second local account makes wrong-identity controls meaningful.
It is part of the declared fixture, not an evaluator-created terminal result.
"""
import base64
import hashlib
import json
from pathlib import Path

from .map_account_profile import validate_account
from .map_account_readout import account_snapshot
from .map_account_observation import protected_users
from .map_query_site import IsolatedMapQuerySite
from .map_reset_guard import MapStateChanged
from .io_utils import atomic_write_json as save

VERSION = 'native-local-existing-accounts-v1'
OTHER = dict(email='control-other@example.test', display_name='Other Local Mapper',
             password='ControlOther-LocalOnly-2026')


def accounts_for(account):
    account = validate_account(account)
    if any(account[k] == OTHER[k] for k in ('email', 'display_name')):
        raise ValueError('Target and control identities must differ')
    return [account, dict(OTHER)]


def seed_source(account):
    # Base64 data prevents user-supplied names/passwords from becoming Ruby code.
    body = base64.b64encode(json.dumps(accounts_for(account)).encode()).decode()
    return '''require "json"
require "base64"
require "time"
specs = JSON.parse(Base64.strict_decode64("'''+body+'''"))
ActiveRecord::Base.transaction do
  stamp = Time.iso8601("2023-03-01T00:00:00Z")
  specs.each do |spec|
    raise "Existing identity collision" if User.where(:email => spec.fetch("email")).exists? || User.where(:display_name => spec.fetch("display_name")).exists?
    user = User.new(:display_name => spec.fetch("display_name"), :email => spec.fetch("email"),
      :email_confirmation => spec.fetch("email"), :pass_crypt => spec.fetch("password"),
      :pass_crypt_confirmation => spec.fetch("password"), :creation_time => stamp,
      :data_public => true, :email_valid => true, :terms_agreed => stamp,
      :terms_seen => true, :tou_agreed => stamp, :languages => ["en-US"],
      :description => "Synthetic local training account, initialized before the task.")
    user.save!
    user.confirm!
  end
end
puts "Declared existing local accounts initialized via native models"
'''


def install(site):
    if site.reset_guard is not None:
        raise ValueError('Existing accounts must precede the reset baseline')
    if not site.state.is_relative_to(Path(site.temporary.name)) or site.rails_command[-5] != 'server':
        raise ValueError('Isolated native Rails site required')
    before = protected_users(site)
    path = site.state/'frontend/app/tmp/existing-local-accounts.rb'
    body = seed_source(site.account)
    path.write_text(body)
    try:
        site.run(site.rails_command[:-5]+['runner','/app/tmp/existing-local-accounts.rb'],
                 'seed_existing_local_accounts',180)
    finally:
        path.unlink(missing_ok=True)
    snapshots = [account_snapshot(site,a['email']) for a in accounts_for(site.account)]
    for spec,snapshot in zip(accounts_for(site.account), snapshots):
        row=snapshot['target']
        if (row is None or any(row[k]!=spec[k] for k in ('email','display_name'))
                or row['email_valid'] is not True or row['status'] not in ('active','confirmed')):
            raise ValueError('Declared confirmed local account missing')
    if protected_users(site,[r['id']for r in before]) != before:
        raise ValueError('Preexisting native users changed during initialization')
    if len(protected_users(site)) != len(before)+2:
        raise ValueError('Unexpected additional fixture users')
    receipt=dict(version=VERSION, installed_before_guard=True,
        synthetic_content=True, original_benchmark_equivalence=False,
        browser_initial_state='signed_out', native_model_initialization=True,
        accounts=snapshots, protected_original_users=before,
        script_sha256=hashlib.sha256(body.encode()).hexdigest(),locale='en-US')
    save(site.logs/'existing-account-initialization.json',receipt)
    return receipt


class IsolatedMapExistingAccountSite(IsolatedMapQuerySite):
    def __init__(self,root,logs,*,account):
        self.account=accounts_for(account)[0]
        self.account_receipt=self.account_users=None
        super().__init__(root,logs,with_tiles=True,with_geographic_baseline=True,track_changes=True)

    def start_frontend(self,port):
        super().start_frontend(port)
        self.account_receipt=install(self)
        self.account_users=protected_users(self)

    def fingerprint(self):
        if self.account_receipt is None or self.account_users is None:
            raise ValueError('Existing local accounts not initialized')
        payload=dict(native=super().fingerprint(),profile=VERSION,account=self.account,
                     target=account_snapshot(self,self.account['email']),
                     other=account_snapshot(self,OTHER['email']))
        return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

    def require_accounts_unchanged(self):
        if protected_users(self)!=self.account_users:
            raise MapStateChanged('Existing account records changed; cold rebuild required')

    def reset_state(self):
        self.require_accounts_unchanged()
        super().reset_state()
        self.require_accounts_unchanged()
