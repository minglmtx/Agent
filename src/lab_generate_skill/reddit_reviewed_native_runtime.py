"""Optional formal runtime for reviewed deterministic Reddit task families.

Public goals/starts are unchanged. Full normal proofs and pre-model native
baselines are mandatory. Public editable draft values are collected only for
terminal evaluation; private SQL/reference data never enters actor/teacher.
"""
import copy
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from lab_generate_skill import reddit_exact_forum as forum
from lab_generate_skill import reddit_exact_forum_runtime as forum_runtime
from lab_generate_skill import reddit_explicit_submission as submission
from lab_generate_skill import reddit_remaining_exact as normal
from lab_generate_skill import site_wiki_rules as wiki
from lab_generate_skill import site_membership_rules as membership
from lab_generate_skill import reddit_hidden_membership as hidden
from lab_generate_skill.io_utils import atomic_write_json
from lab_generate_skill.reddit_protected_chunks import require_restored_proof, validate_snapshot
from lab_generate_skill.site_database import select_rows

VERSION = 'reddit-reviewed-native-formal-runtime-v1'
FAMILIES = ('exact_forum', 'explicit_submission', 'wiki_creation', 'subscription', 'hidden_membership')
FIELDS = ('exact_forum_creation', 'explicit_submission', 'wiki', 'membership')
OTHER_FIELDS = ('reddit_native_task', 'query', 'preferences', 'forum_creation', 'submission', 'search',
    'cart', 'vote', 'fork_creation', 'project_creation', 'group_creation', 'issue_creation',
    'ref_creation', 'account_change', 'checkout', 'order', 'map_export')


def family(contract):
    if contract.get('domain') != 'reddit' or sum(key in contract for key in FIELDS) != 1:
        raise ValueError('One reviewed Reddit family required')
    if any(contract.get(key) for key in OTHER_FIELDS):
        raise ValueError('Reviewed Reddit family cannot mix another task profile')
    if 'exact_forum_creation' in contract:
        forum.validate_contract(contract)
        return 'exact_forum'
    if 'explicit_submission' in contract:
        submission.validate_contract(contract)
        return 'explicit_submission'
    if 'wiki' in contract:
        wiki.validate_contract(contract)
        return 'wiki_creation'
    if contract['membership'].get('collection') == 'hidden_forums':
        hidden.validate(contract)
        return 'hidden_membership'
    spec = contract['membership']
    if (set(spec) != {'object_id', 'object_path', 'desired_present'}
            or type(spec['object_id']) is not int or spec['object_id'] <= 0
            or type(spec['desired_present']) is not bool or not isinstance(spec['object_path'], str)
            or not spec['object_path'].startswith('/f/')):
        raise ValueError('Exact local subscription membership required')
    return 'subscription'


def enabled(contract):
    if 'reviewed_reddit_family' not in contract:
        return False
    kind = family(contract)
    if (contract['reviewed_reddit_family'] != kind or contract.get('runtime_version') != VERSION
            or contract.get('completion') != {} or contract.get('shared_runtime_ready') is not False
            or contract.get('heldout_quarantine') is not False or contract.get('eligible_for_training') is not False):
        raise ValueError('Explicit development compatibility binding required')
    return True


def bind_normal_contract(original, *, admission_path):
    if (original.get('eligible_for_training') is not False or original.get('heldout_quarantine') is not False
            or any(key in original for key in ('reviewed_reddit_family', 'completion', 'runtime_version', 'shared_runtime_ready', 'admission_result'))):
        raise ValueError('Unmodified reviewed CPU source contract required')
    value = copy.deepcopy(original)
    value.update(completion={}, runtime_version=VERSION, reviewed_reddit_family=family(original),
        shared_runtime_ready=False, admission_result=str(admission_path))
    return value


def _path(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Original recorded start required')
    parsed = urlsplit(value)
    return (parsed.path or '/') + ('?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')


def require_original_binding(contract, original, inventory):
    expected = bind_normal_contract(original, admission_path=contract.get('admission_result', ''))
    if json.dumps(contract, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError('Compatibility changed an original task or declared revision')
    source_goal = contract.get('original_goal') if contract.get('task_text_changed') else contract.get('goal')
    if (not isinstance(inventory, dict) or inventory.get('task_id') != contract.get('source_task_id')
            or inventory.get('domain') != 'reddit' or inventory.get('heldout_quarantine') is not False
            or inventory.get('goal') != source_goal or inventory.get('source_trace_ids') != contract.get('source_trace_ids')
            or [_path(url) for url in inventory.get('recorded_start_urls', [])] != contract.get('recorded_start_paths')
            or not contract.get('recorded_start_paths') or contract.get('start_path') != contract['recorded_start_paths'][0]):
        raise ValueError('Authoritative original goal, traces or first start changed')


def require_admission(contract, proof):
    if not enabled(contract):
        raise ValueError('Reviewed native Reddit binding required')
    kind = family(contract)
    if kind == 'explicit_submission':
        submission.require_admission(contract, proof)
        require_restored_proof(proof)
    elif kind == 'hidden_membership':
        hidden.require_admission(contract, proof)
        # Existing legacy hidden proof lacks this protection. It must not be
        # promoted using another source's table baseline or a new schema flag.
        require_restored_proof(proof)
    else:
        normal.require_admission(contract, proof)
    if (type(proof.get('actor_attempts')) is not int or proof['actor_attempts'] != 0
            or type(proof.get('api_calls')) is not int or proof['api_calls'] != 0):
        raise ValueError('Zero-model zero-API native controls required')
    return True


def feedback(judgment):
    return {'status': judgment['status'], 'reward': judgment['reward'], 'reason': judgment.get('reason'),
        'checks': [{'name': key, 'passed': value} for key, value in judgment.get('checks', {}).items()],
        'action_sequence_provided': False, 'private_reference_values_provided': False}


def wiki_records(site):
    """Full original revision rows cannot be hidden by equal latest bodies."""
    return {table: [row['row'] for row in select_rows(site,
                'SELECT row_to_json(r) AS row FROM ' + table + ' r ORDER BY id')]
            for table in ('wiki_pages', 'wiki_revisions')}


def original_wiki_records_unchanged(before, after, initial, final):
    before_pages = {row['id'] for row in initial['pages']}
    added = {row['id'] for row in final['pages']} - before_pages
    if len(added) > 1:
        return False
    for table in ('wiki_pages', 'wiki_revisions'):
        old = {row['id']: row for row in before[table]}
        new = {row['id']: row for row in after[table]}
        if any(new.get(key) != value for key, value in old.items()):
            return False
        for key in new.keys() - old.keys():
            row = new[key]
            if table == 'wiki_pages':
                if row['id'] not in added:
                    return False
            elif row.get('page_id') not in added or row.get('user_id') != initial['user_id']:
                return False
    return True


def submission_vote_records(site, fingerprint):
    """Read every native vote row; hashes must match the full-table scan.

    Native Submission creates one author upvote automatically. Whole-table
    invariance cannot protect a legitimate new post, so preserve all old full
    rows and allow only that exact new relation. These records are private.
    """
    values = select_rows(site, 'SELECT row_to_json(r) AS row, md5(row_to_json(r)::text) AS row_hash '
                              'FROM submission_votes r ORDER BY id')
    known = set(); prior = 0
    for item in values:
        row = item.get('row') if isinstance(item, dict) else None
        if (not isinstance(row, dict) or set(row) != {'id','upvote','timestamp','user_id','ip','submission_id'}
                or any(type(row[k]) is not int or row[k] <= 0 for k in ('id','user_id','submission_id'))
                or row['id'] <= prior or type(row['upvote']) is not bool
                or not isinstance(row['timestamp'], str) or not row['timestamp']
                or (row['ip'] is not None and not isinstance(row['ip'], str))
                or not isinstance(item.get('row_hash'), str)
                or not re.fullmatch('[0-9a-f]{32}', item['row_hash'])
                or (row['submission_id'],row['user_id']) in known):
            raise RuntimeError('Incomplete or malformed native full submission-vote records')
        prior=row['id'];known.add((row['submission_id'],row['user_id']))
    native={'count':len(values),'digest':hashlib.md5(''.join(v['row_hash'] for v in values).encode()).hexdigest()}
    if native != fingerprint:
        raise RuntimeError('Native vote rows do not match full protected-table coverage')
    return copy.deepcopy(values)


def automatic_author_vote_only(before, after, initial, final):
    """Preserve every old vote/full-row hash and every unrelated account."""
    old={v['row']['id']:v for v in before};new={v['row']['id']:v for v in after}
    if any(new.get(key)!=value for key,value in old.items()):return False
    added=[new[key]['row']for key in new.keys()-old.keys()]
    if not added:return True
    posts=final.get('added')
    if len(added)!=1 or not isinstance(posts,list) or len(posts)!=1:return False
    post=posts[0];vote=added[0]
    return (type(post.get('id'))is int and post['id']>0
            and post.get('user_id')==initial['user_id']
            and vote['submission_id']==post['id']
            and vote['user_id']==initial['user_id'] and vote['upvote']is True)


class ReviewedNativeHooks:
    def __init__(self, contract, proof, directory):
        require_admission(contract, proof)
        self.contract, self.proof, self.directory = copy.deepcopy(contract), copy.deepcopy(proof), Path(directory)
        self.kind = family(contract)
        self.before = self.protected_before = self.submission_before = self.all_before = None
        self.public_terminal = None
        self.wiki_before = None
        self.vote_before = None
        self.exact = forum_runtime.ExactForumHooks(contract, proof, directory) if self.kind == 'exact_forum' else None

    def _state(self, site, username, baseline=None):
        if self.kind == 'explicit_submission': return submission.state(site, username, baseline)
        if self.kind == 'wiki_creation': return wiki.wiki_state(site, username)
        return membership.membership_state(site, username, 'hidden_forums' if self.kind == 'hidden_membership' else None)

    def verify_baseline(self, site, username):
        if self.exact is not None:
            self.exact.verify_baseline(site, username)
            return
        value = self._state(site, username)
        protected = forum_runtime.protected_snapshot(site)
        all_before = normal.subscriptions(site) if self.kind == 'subscription' else None
        # Independently preserve all original submissions for the other task
        # families; allowed creations are checked by the exact evaluator.
        submissions = value if self.kind == 'explicit_submission' else submission.state(site, username)
        wiki_before = wiki_records(site) if self.kind == 'wiki_creation' else None
        publication = self.kind == 'explicit_submission' and self.contract['explicit_submission']['kind'] == 'published_text'
        vote_before = submission_vote_records(site,protected['submission_votes']) if publication else None
        atomic_write_json(self.directory/'reviewed-reddit-private-before.json',
            {'state': value, 'protected': protected, 'all_account_subscriptions': all_before,
             'submission_state': submissions, 'complete_wiki_records': wiki_before,
             'complete_submission_vote_records': vote_before})
        cycle = self.proof['cycles'][0]
        if (value != cycle['initial_state'] or protected != cycle['private_protected_before']
                or (self.kind == 'subscription' and all_before != cycle['all_account_initial'])):
            raise RuntimeError('Reviewed task differs from its complete native two-fresh baseline')
        if self.kind == 'explicit_submission': submission.validate_initial(self.contract, value)
        elif self.kind == 'wiki_creation': wiki.validate_initial(self.contract, value)
        elif self.kind == 'subscription': membership.validate_target(site, self.contract)
        else: hidden.verify_reference(site, self.contract)
        self.before, self.protected_before, self.submission_before, self.all_before = copy.deepcopy((value, protected, submissions, all_before))
        self.wiki_before = copy.deepcopy(wiki_before)
        self.vote_before = copy.deepcopy(vote_before)

    def capture_terminal(self, page):
        # Public form values are native observations of the final document,
        # never a private expected-value injection and never an actor input.
        if self.kind == 'explicit_submission':
            self.public_terminal = page.evaluate(submission.READ)
            atomic_write_json(self.directory/'reviewed-reddit-terminal-public-draft.json', self.public_terminal)

    def score_terminal(self, site, username, page, *, runtime_error=None):
        if self.exact is not None:
            return self.exact.score_terminal(site, username, page, runtime_error=runtime_error)
        if self.before is None:
            raise RuntimeError('Verified native baseline required before model and terminal scoring')
        after = self._state(site, username, self.before)
        protected_after = forum_runtime.protected_snapshot(site)
        all_after = normal.subscriptions(site) if self.kind == 'subscription' else None
        submissions = after if self.kind == 'explicit_submission' else submission.state(site, username, self.submission_before)
        wiki_after = wiki_records(site) if self.kind == 'wiki_creation' else None
        vote_after = submission_vote_records(site,protected_after['submission_votes']) if self.vote_before is not None else None
        atomic_write_json(self.directory/'reviewed-reddit-private-after.json',
            {'state': after, 'protected': protected_after, 'all_account_subscriptions': all_after,
             'submission_state': submissions, 'complete_wiki_records': wiki_after,
             'complete_submission_vote_records': vote_after})
        if self.kind == 'explicit_submission':
            judgment = submission.evaluate(self.contract, page, self.before, after,
                site_origin=site.url, public=self.public_terminal, runtime_error=runtime_error)
            allowed = set()
        elif self.kind == 'wiki_creation':
            judgment = wiki.evaluate_wiki(self.contract, page, self.before, after,
                site_origin=site.url, runtime_error=runtime_error)
            allowed = {'wiki_pages', 'wiki_revisions'}
        elif self.kind == 'subscription':
            if runtime_error:
                judgment = {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Runtime failure'}
            else:
                judgment = normal.evaluate(self.contract, page, self.before, after, site_origin=site.url,
                    all_before=self.all_before, all_after=all_after)
            allowed = {'forum_subscriptions'}
        else:
            judgment = hidden.evaluate_hidden_membership(self.contract, page, self.before, after,
                site_origin=site.url, runtime_error=runtime_error)
            allowed = {'hidden_forums'}
        validate_snapshot(self.protected_before); validate_snapshot(protected_after)
        integrity = all((automatic_author_vote_only(self.vote_before,vote_after,self.before,after)
                         if table=='submission_votes' and self.vote_before is not None
                         else self.protected_before[table] == protected_after[table])
                        for table in forum_runtime.TABLES if table not in allowed)
        if self.kind == 'explicit_submission':
            integrity = integrity and submissions['protected_content'] == self.submission_before['protected_content']
        else:
            integrity = integrity and submissions == self.submission_before
        if self.kind == 'wiki_creation':
            integrity = integrity and original_wiki_records_unchanged(self.wiki_before, wiki_after, self.before, after)
        # Existing family evaluators independently constrain every allowed
        # changed row/relation, including all other accounts. An unrelated edit
        # can never be hidden by treating the whole table as allowed.
        return judgment, integrity
