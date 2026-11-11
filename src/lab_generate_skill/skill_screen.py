"""Offline candidate triage; heuristic flags are not semantic correctness labels."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import random
import re

from .io_utils import atomic_write_json, iter_jsonl
from .schemas import CompactSkill

VERSION = 'offline-skill-screen-v2'
BAD_STATE = r'\b404\b|not[- ]found|no (?:search )?results|permission denied|access denied'
ABSENCE = r'(?:report\w*|conclud\w*|assum\w*|declar\w*|supports?)\b.{0,120}(?:not (?:be )?found|does not exist|doesn.t exist|unavailable|absent|no matching)'
FINISH = r'(?:report|declare|mark|claim)\w*\b.{0,35}(?:success|complet)|\b(?:terminate|end) (?:the )?(?:task|episode|interaction)\b|\bstop(?: immediately)?(?:[.!;]|$)|\bstop (?:the )?(?:task|episode|interaction)\b'
PATH_CHECK = r'(?:check|verify|validat|confirm|correct|valid|exact)\w*\b.{0,75}(?:path|url|address|username)|(?:path|url|address|username).{0,60}(?:correct|valid|match)'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(1024*1024), b''): h.update(part)
    return h.hexdigest()


def normalize(text):
    return re.sub(r'\s+', ' ', text).strip().casefold()


def skill_text(skill):
    return '\n'.join(str(skill.get(k, '')) for k in ('title','principle','when_to_apply'))


def source_summary(trace):
    observations, actions = [], []
    for msg in trace.get('messages', []):
        content = msg.get('content', '')
        try: parsed = json.loads(content) if isinstance(content, str) else content
        except (ValueError, TypeError): parsed = {}
        if not isinstance(parsed, dict): parsed = {}
        if msg.get('role') == 'user' and 'axtree' in parsed:
            observations.append({'heading': parsed['axtree'].split('\n')[0][:500],
                                 'last_action_error': str(parsed.get('last_action_error') or '')[:500]})
        if msg.get('role') == 'assistant':
            actions.append(str(msg.get('action_payload') or parsed.get('action') or '')[:1500])
    return {'trace_id': trace['trace_id'], 'goal': trace.get('task_instruction', ''),
            'outcome': trace.get('evaluation_outcome'), 'rounds': trace.get('rounds'),
            'final_response': str((trace.get('task_output') or {}).get('response') or '')[:1500],
            'last_observations': observations[-2:], 'last_actions': actions[-3:],
            'terminal_observation_available': (trace.get('provenance') or {}).get('terminal_observation_available')}


def assess(skill, source):
    """Only specific content hazards cause a hold; source concerns are soft flags."""
    flags = []
    def add(code, severity, excerpt):
        if not any(x['code'] == code for x in flags):
            flags.append({'code':code, 'severity':severity, 'excerpt':excerpt[:500]})
    try: CompactSkill.model_validate(skill)
    except ValueError: add('schema_or_length', 'hold', 'Candidate does not satisfy CompactSkill schema')
    text = skill_text(skill)
    bid = re.search(r'\b(?:click|fill|hover|select_option|upload_file|press)\s*\(\s*[\x22\x27]?\d+[\x22\x27]?\s*[,)]|\b(?:bid|element id)\s*[=:]?\s*[\x22\x27]?\d+\b', text, re.I)
    if bid: add('literal_element_id', 'hold', bid.group())
    for url in re.findall(r'https?://[^\s<>\x22\x27`]+', text):
        if re.search(r'ec2-|compute\.amazonaws|localhost|127\.0\.0\.1|://\d{1,3}(?:\.\d{1,3}){3}|:\d{4,5}\b', url, re.I):
            add('deployment_address', 'hold', url)
        else: add('absolute_url_check', 'flag', url)
    goal = source.get('goal', '')
    user = re.search(r'\buser profile of\s+[\x22\x27]?([\w-]+)', goal, re.I)
    if user and len(user[1]) >= 4 and re.search(r'\b'+re.escape(user[1])+r'\b', text, re.I):
        add('instance_username', 'hold', user[1])
    # Dates/record numbers shared with the task are flags, not automatic deletions.
    values = set(re.findall(r'\b\d{4}-\d{2}-\d{2}\b|\b\d{5,}\b', goal))
    for value in sorted(values):
        if re.search(r'(?<!\w)'+re.escape(value)+r'(?!\w)', text):
            add('task_specific_value', 'flag', value)
    principle = skill.get('principle', '')
    for sentence in re.split(r'(?<=[.!?;])\s+|\n', principle):
        if not re.search(BAD_STATE, sentence, re.I): continue
        # Corrective/negated statements must not be confused with endorsements.
        if re.search(r'\b(?:do not|don.t|never|avoid|rather than|instead of|does not imply|does not mean)\b', sentence, re.I): continue
        if re.search(ABSENCE, sentence, re.I):
            guarded = re.search(PATH_CHECK, principle, re.I)
            recovery = re.search(r'(?:continue|search again|reassess|verify|check|locate).{0,130}before (?:conclud|declar|report)', sentence, re.I)
            # A search returning no matches is a reportable observation, not
            # necessarily a false assertion that the target does not exist.
            empty_search = re.search(r'no (?:matching|matches|(?:search )?results)', sentence, re.I)
            add('failure_implies_absence', 'flag' if guarded or recovery or empty_search else 'hold', sentence)
        verifies_recovery = re.search(r'(?:verify|confirm|check).{0,80}(?:resulting|new|requested|target|destination)', sentence, re.I)
        if re.search(FINISH, sentence, re.I) and not verifies_recovery:
            # Reporting a genuine unavailable resource may satisfy some tasks;
            # this is suspected unsafe termination, not a proven bad label.
            add('failure_implies_completion', 'hold', sentence)
    if source.get('outcome') == 'correct':
        last = (source.get('last_observations') or [{}])[-1]
        if re.search(r'\b404\b|not found|access denied|permission denied', last.get('heading',''), re.I):
            add('source_success_error_page', 'flag', last.get('heading',''))
        if last.get('last_action_error'):
            add('source_success_last_action_error', 'flag', last['last_action_error'])
        response = source.get('final_response', '')
        if re.search(r'could not (?:be )?find|could not be found|couldn.t find|unable to|could not complete|does not exist|not found|cannot (?:access|find|complete)', response, re.I):
            add('source_success_negative_report', 'flag', response)
    return flags


def local_embeddings(texts, model_path):
    # A local directory and strict offline settings prevent downloads/API calls.
    if not model_path.is_dir(): raise ValueError('Embedding model must be an existing local directory')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    model = SentenceTransformer(str(model_path), device='cpu', local_files_only=True)
    chunks, owners = [], []
    max_length = model.max_seq_length
    for i, text in enumerate(texts):
        tokens = model.tokenizer.encode(text, add_special_tokens=False, truncation=False)
        width = max_length - 32
        for start in range(0, max(1,len(tokens)), width):
            chunk = model.tokenizer.decode(tokens[start:start+width], skip_special_tokens=True)
            if len(model.tokenizer.encode(chunk)) > max_length:
                raise ValueError('Embedding chunk would truncate; reduce chunk width')
            chunks.append(chunk); owners.append(i)
    encoded = model.encode(chunks, batch_size=32, normalize_embeddings=True, show_progress_bar=True)
    vectors = np.zeros((len(texts), encoded.shape[1]), dtype=np.float32)
    for i, vector in zip(owners, encoded): vectors[i] += vector
    vectors /= np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-12)
    return vectors, {'chunk_count':len(chunks), 'multi_chunk_skills':sum(n>1 for n in Counter(owners).values()),
                     'model_max_seq_length':max_length, 'truncated_skills':0}


def group_weights(rows, vectors, threshold=.92, mass_cap=3):
    from .clustering import _complete_linkage_groups
    by_domain = defaultdict(list)
    for i,row in enumerate(rows): by_domain[row['domain']].append(i)
    groups = []
    for domain, indices in sorted(by_domain.items()):
        for members in _complete_linkage_groups(indices,vectors,threshold):
            eligible=[i for i in members if rows[i]['decision']!='hold']
            # Weighting retains task/condition diversity; it does not merge skills.
            weight=min(1.0,mass_cap/len(eligible)) if eligible else 0.0
            gid=f'similar_{len(groups)+1:05d}'
            for i in members:
                rows[i]['similarity_group']=gid
                rows[i]['sample_weight']=0.0 if rows[i]['decision']=='hold' else weight
            groups.append({'group_id':gid,'domain':domain,'size':len(members),'eligible_count':len(eligible),
                           'suggested_weight':weight,'generation_ids':[rows[i]['generation_id'] for i in members]})
    return groups


def write_jsonl(path, rows):
    # New audit directory only; these files never replace paid ledgers/banks.
    with path.open('w') as f:
        for row in rows: f.write(json.dumps(row,ensure_ascii=False)+'\n')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, action='append', required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--embedding-model',type=Path,required=True)
    p.add_argument('--threshold',type=float,default=.92)
    p.add_argument('--group-mass-cap',type=int,default=3)
    p.add_argument('--seed',type=int,default=42)
    args=p.parse_args(argv)
    if not 0<args.threshold<1 or args.group_mass_cap<1: p.error('Invalid threshold or group mass cap')
    if args.output_dir.exists(): p.error('Use a new output directory; existing audits are immutable')
    from .config import load_settings
    from .openrouter_distill import output_lock
    settings=[load_settings(path) for path in args.config]
    settings.sort(key=lambda s:str(s.paths.artifacts_dir))
    candidates=[]; sources={}; files={}; seen=set()
    # Snapshot while holding the same locks as paid extraction, then release.
    with ExitStack() as stack:
        for s in settings: stack.enter_context(output_lock(s.paths.artifacts_dir))
        for s in settings:
            path=s.paths.artifacts_dir/'raw_candidates.jsonl'; files[str(path)]=digest(path)
            needed=set()
            for row in iter_jsonl(path):
                if row['generation_id'] in seen: raise ValueError('Duplicate generation ID across inputs')
                seen.add(row['generation_id']); candidates.append(row); needed.update(row['trace_ids'])
            for domain in s.collection.domains:
                path=s.paths.trajectories_dir/f'{domain}.jsonl'
                # Hash and stream each file once, retain only compact audit context.
                h=hashlib.sha256()
                with path.open('rb') as f:
                    for line in f:
                        h.update(line)
                        row=json.loads(line)
                        if row['trace_id'] in needed: sources[row['trace_id']]=source_summary(row)
                files[str(path)]=h.hexdigest()
    args.output_dir.mkdir(parents=True)
    rows=[]
    for candidate in candidates:
        if len(candidate['trace_ids'])!=1: raise ValueError('Expected one source per compact candidate')
        trace_id=candidate['trace_ids'][0]
        if trace_id not in sources: raise ValueError(f'Missing source {trace_id}')
        source=sources[trace_id]; flags=assess(candidate['candidate'],source)
        row={**candidate,'source':source,'flags':flags,
             'decision':'hold' if any(f['severity']=='hold' for f in flags) else 'keep_flagged' if flags else 'keep'}
        rows.append(row)
    print(json.dumps({'stage':'rules_complete','candidates':len(rows),'decisions':dict(Counter(r['decision'] for r in rows))}),flush=True)
    vectors,embedding_info=local_embeddings([skill_text(r['candidate']) for r in rows], args.embedding_model)
    groups=group_weights(rows,vectors,args.threshold,args.group_mass_cap)
    import numpy as np
    np.save(args.output_dir/'embeddings.npy',vectors)
    write_jsonl(args.output_dir/'audit.jsonl',rows)
    write_jsonl(args.output_dir/'held_candidates.jsonl',[r for r in rows if r['decision']=='hold'])
    write_jsonl(args.output_dir/'flagged_candidates.jsonl',[r for r in rows if r['flags']])
    allowed={r['generation_id'] for r in rows if r['decision']!='hold'}
    write_jsonl(args.output_dir/'eligible_candidates.jsonl',[r for r in candidates if r['generation_id'] in allowed])
    write_jsonl(args.output_dir/'sampling_weights.jsonl',[
        {k:r[k] for k in ('generation_id','trace_ids','domain','decision','similarity_group','sample_weight')} for r in rows])
    atomic_write_json(args.output_dir/'similarity_groups.json',groups)
    rng=random.Random(args.seed); sample=[]
    for domain in sorted({r['domain'] for r in rows}):
        for outcome in ('correct','incorrect'):
            pool=[r for r in rows if r['domain']==domain and r['source']['outcome']==outcome and not r['flags']]
            sample.extend(rng.sample(pool,min(2,len(pool))))
    write_jsonl(args.output_dir/'unflagged_review_sample.jsonl',sample)
    distribution=lambda subset:dict(Counter(f"{r['domain']}:{r['source']['outcome']}" for r in subset))
    exact=Counter((r['domain'],normalize(skill_text(r['candidate']))) for r in rows)
    report={'version':VERSION,'candidates':len(rows),'decisions':dict(Counter(r['decision'] for r in rows)),
            'rule_counts':dict(Counter(f['code'] for r in rows for f in r['flags'])),
            'before_distribution':distribution(rows),'eligible_distribution':distribution([r for r in rows if r['decision']!='hold']),
            'similarity_groups':len(groups),'non_singleton_groups':sum(g['size']>1 for g in groups),
            'largest_group':max((g['size'] for g in groups),default=0),
            'downweighted_candidates':sum(0<r['sample_weight']<1 for r in rows),
            'suggested_effective_sample_mass':sum(r['sample_weight'] for r in rows),
            'exact_duplicate_excess':sum(n-1 for n in exact.values()),
            'parameters':{'threshold':args.threshold,'group_mass_cap':args.group_mass_cap,'seed':args.seed,
                          'embedding_model':str(args.embedding_model),'device':'cpu','linkage':'complete','within_domain':True},
            'embedding':embedding_info,'source_sha256':files,'script_sha256':digest(Path(__file__)),
            'api_calls':0,'gpu_used':False,
            'limitations':['Rule hits are suspected risks, not a measured semantic error rate.',
                           'Unflagged does not mean semantically verified. No automatic content rewriting.',
                           'Missing terminal observations and unexecuted corrective suggestions are not exclusion criteria.',
                           'Similarity groups are heuristic frequency controls, not proof of equivalence.',
                           'Weights are suggestions; a future SFT sampler must explicitly consume them.',
                           'This is candidate screening, not a task-conditioned generator SFT dataset.']}
    atomic_write_json(args.output_dir/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},ensure_ascii=False,indent=2),flush=True)
    return 0
