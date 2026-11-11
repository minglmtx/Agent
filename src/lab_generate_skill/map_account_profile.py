"""Public local-account environment profiles, separate from private references."""
from copy import deepcopy


def validate_account(account):
    if (not isinstance(account,dict) or set(account)!={'email','display_name','password'}
            or any(not isinstance(v,str) or not v or '\n'in v or '\r'in v for v in account.values())
            or not account['email'].endswith('@example.test')):
        raise ValueError('Complete local training account required')
    return deepcopy(account)


def profile_for_contracts(rows):
    if not rows or any(c.get('domain')!='map' or c.get('candidate_completion',{}).get('family')!='account_signup' for c in rows):
        raise ValueError('Dedicated native signup manifest required')
    accounts=[validate_account(c['candidate_completion']['public_account'])for c in rows]
    if any(a!=accounts[0]for a in accounts):
        raise ValueError('Different account/inbox profiles require separate manifests')
    return {'map_account':accounts[0]}


def existing_profile_for_contracts(rows):
    if not rows or any(c.get('domain')!='map' or c.get('candidate_completion',{}).get('family')!='account_login'for c in rows):
        raise ValueError('Dedicated existing-account login manifest required')
    accounts=[validate_account(c['candidate_completion']['public_account'])for c in rows]
    if any(a!=accounts[0]for a in accounts):raise ValueError('Different login fixtures require separate manifests')
    return {'map_existing_account':accounts[0]}
