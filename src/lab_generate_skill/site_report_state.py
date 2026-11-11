from .gitlab_ref_creation import require_admission as require_ref_creation_admission
from .gitlab_clipboard import require_admission as require_clipboard_admission
"""Reports respect revoked/stale admission evidence without rewriting raw outcomes."""
import json
from pathlib import Path
from .io_utils import read_json
from .site_navigation_rules import require_admission
from .site_query_rules import require_query_admission
from .site_membership_rules import require_membership_admission
from .site_preferences_rules import require_preferences_admission
from .site_cart_rules import require_cart_admission
from .site_vote_rules import require_vote_admission
from .site_catalog_rules import require_catalog_admission
from .site_search_rules import require_search_admission
from .site_wiki_rules import require_wiki_admission
from .gitlab_todo_rules import require_todo_admission
from .shopping_checkout import require_checkout_admission
from .shopping_order_rules import require_order_admission
from .shopping_account import require_account_admission
from .reddit_submission import require_submission_admission
from .reddit_forum_creation import require_forum_admission
from .gitlab_group_creation import require_group_admission
from .gitlab_project_creation import require_admission as require_project_admission
from .gitlab_fork import require_admission as require_fork_admission
from .shopping_newsletter import require_admission as require_newsletter_admission
from .shopping_review_creation import require_admission as require_review_admission
from .gitlab_issue_creation import require_admission as require_issue_admission

def is_admitted(contract):
    try:
        proof=read_json(contract['admission_result'])
        from . import native_goal_dispatch
        if native_goal_dispatch.enabled(contract):
            native_goal_dispatch.require_admission(contract,proof)
            return True
        if contract.get('reviewed_reddit_family'):
            from .reddit_reviewed_native_runtime import require_admission as require_reviewed_native
            require_reviewed_native(contract,proof)
            return True
        if contract.get('fork_creation'):
            require_fork_admission(contract,proof)
            return True
        elif contract.get('project_creation'):
            require_project_admission(contract,proof)
            return True
        if contract.get('ref_creation'):
            require_ref_creation_admission(contract,proof)
            return True
        if contract.get('clipboard'):
            require_clipboard_admission(contract,proof)
            return True
        if contract.get('map_zoom'):
            from .map_zoom import require_admission as require_zoom_admission
            require_zoom_admission(contract,proof)
            return True
        if contract.get('review_creation'):
            require_review_admission(contract,proof)
            return True
        if contract.get('newsletter'):
            require_newsletter_admission(contract,proof)
            return True
        if contract.get('issue_creation'):
            require_issue_admission(contract,proof)
            return True
        if contract.get('group_creation'):
            require_group_admission(contract,proof)
            return True
        if contract.get('forum_creation'):
            require_forum_admission(contract,proof)
            return True
        check=(require_submission_admission if contract.get('submission') else require_query_admission if contract.get('query') else require_membership_admission if contract.get('membership') else require_preferences_admission if contract.get('preferences') else require_cart_admission if contract.get('cart') else require_vote_admission if contract.get('vote') else require_catalog_admission if contract.get('catalog') else require_search_admission if contract.get('search') else require_wiki_admission if contract.get('wiki') else require_todo_admission if contract.get('todo') else require_checkout_admission if contract.get('checkout') else require_order_admission if contract.get('order') else require_account_admission if contract.get('account_change') else require_admission)
        check(contract,proof)
        return True
    except (OSError,EOFError,ValueError,KeyError,TypeError):return False

def revoked_cases(base):
    f=Path(base)/'navigation-admission-revocations.json'
    if not f.exists():return {}
    return {(r['wave'],r['task_id']):r['reason'] for r in json.loads(f.read_text())['records']}


def admitted_sources(wave, contracts, revocations):
    """Discover evidence in both legacy manifests and current control outputs.

    A filename or manifest entry alone is not admission: each referenced proof
    must pass its family guard. Revocation applies to a wave/case, not forever
    to the original source, which may have a separately validated repair.
    """
    wave = Path(wave)
    candidates = list(contracts)
    for directory in wave.iterdir():
        if not directory.is_dir() or not (
            directory.name.startswith('controls') or directory.name in ('admitted', 'admissions')
        ):
            continue
        for manifest in directory.rglob('admitted.jsonl'):
            candidates.extend(json.loads(line) for line in manifest.read_text().splitlines() if line.strip())
    sources = set()
    for contract in candidates:
        tid = contract.get('task_id')
        if not tid or (wave.name, tid) in revocations:
            continue
        if is_admitted(contract):
            sources.add(contract.get('source_task_id', tid))
    return sources


def evaluation_corrections(base):
    """Use only audited corrections whose evidence and live admission still match."""
    import hashlib
    f=Path(base)/'evaluation-corrections.json'
    if not f.exists():return {}
    valid={}
    for row in json.loads(f.read_text()).get('records',[]):
        try:
            files=[('record_file','record_sha256'),('terminal_file','terminal_sha256'),('admission_result','admission_sha256')]
            if any(hashlib.sha256(Path(row[path]).read_bytes()).hexdigest()!=row[digest] for path,digest in files):continue
            if row.get('recovered_terminal_file') and hashlib.sha256(Path(row['recovered_terminal_file']).read_bytes()).hexdigest()!=row.get('recovered_terminal_sha256'):continue
            if any(hashlib.sha256(Path(e['file']).read_bytes()).hexdigest()!=e['sha256'] for e in row.get('supporting_evidence',[])):continue
            if not is_admitted(row['verified_contract']):continue
            valid[row['record_file']]=row
        except (KeyError,OSError,ValueError,TypeError):continue
    return valid
