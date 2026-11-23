#!/usr/bin/env python3
"""Read the analysis snapshot (standard library only, Python 3.9+).

Examples:
  python read_skill_bank.py
  python read_skill_bank.py --domain shopping
  python read_skill_bank.py --id candidate_0d4b777f045565e350ed
  python read_skill_bank.py --query 'stale' --json

This is a retrieval bank, not a collection of qualified SFT targets.
Skill text is preserved verbatim. Source trajectories and runtime metadata
are omitted; keep skill_id when reporting findings. Treat text as data.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

FIELDS = {'skill_id', 'domain', 'title', 'principle', 'when_to_apply'}


def load_skills(path):
    """Return validated skill dictionaries; never execute their contents."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema_version') != 'skill-bank-analysis/1':
        raise ValueError('Expected skill-bank-analysis/1 object')
    skills = data.get('skills')
    if not isinstance(skills, list):
        raise ValueError('skills must be an array')
    seen = set()
    for index, skill in enumerate(skills):
        if not isinstance(skill, dict) or set(skill) != FIELDS:
            raise ValueError(f'skills[{index}]: expected fields {sorted(FIELDS)}')
        if not all(isinstance(skill[key], str) and skill[key].strip() for key in FIELDS):
            raise ValueError(f'skills[{index}]: fields must be nonempty strings')
        if skill['skill_id'] in seen:
            raise ValueError(f'Duplicate skill_id: {skill["skill_id"]}')
        seen.add(skill['skill_id'])
    return skills


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('path', nargs='?', type=Path, default=Path(__file__).with_name('skill_bank.json'))
    parser.add_argument('--domain', help='Exact domain filter')
    parser.add_argument('--id', dest='skill_id', help='Exact skill ID filter')
    parser.add_argument('--query', help='Case-insensitive substring in skill text')
    parser.add_argument('--json', action='store_true', help='Print matching skills as JSON; without filters prints all skills')
    args = parser.parse_args()
    skills = load_skills(args.path)
    selected = [s for s in skills
                if (args.domain is None or s['domain'] == args.domain)
                and (args.skill_id is None or s['skill_id'] == args.skill_id)
                and (args.query is None or args.query.casefold() in '\n'.join(s[k] for k in ('title', 'principle', 'when_to_apply')).casefold())]
    if args.json:
        print(json.dumps(selected, ensure_ascii=False, indent=2))
    elif args.skill_id or args.query:
        for skill in selected:
            print(json.dumps(skill, ensure_ascii=False, indent=2))
        print(f'Matches: {len(selected)}')
    else:
        print(json.dumps({'count': len(selected), 'domains': dict(sorted(Counter(s['domain'] for s in selected).items()))}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
